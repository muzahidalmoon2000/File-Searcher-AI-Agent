import requests
import os
from semantic_search import rank_files_by_similarity

def get_user_email(token):
    headers = {"Authorization": f"Bearer {token}"}
    res = requests.get("https://graph.microsoft.com/v1.0/me", headers=headers)
    if res.status_code == 200:
        return res.json().get("mail") or res.json().get("userPrincipalName")
    return None


def search_all_files(token, query):
    headers = {"Authorization": f"Bearer {token}"}
    all_results = []

    # 1. Personal OneDrive search
    me_res = requests.get(f"https://graph.microsoft.com/v1.0/me/drive/root/search(q='{query}')", headers=headers)
    if me_res.status_code == 200:
        all_results += tag_site_id(me_res.json().get("value", []), "personal")

    # 2. Search all SharePoint sites
    sites_url = "https://graph.microsoft.com/v1.0/sites?search=*"
    all_sites = []
    all_drives = []

    while sites_url:
        sites_res = requests.get(sites_url, headers=headers)
        if sites_res.status_code == 200:
            sites_data = sites_res.json()
            for site in sites_data.get("value", []):
                site_id = site["id"]
                all_sites.append(site_id)

                drives_url = f"https://graph.microsoft.com/v1.0/sites/{site_id}/drives"
                drives_res = requests.get(drives_url, headers=headers)
                if drives_res.status_code == 200:
                    for drive in drives_res.json().get("value", []):
                        all_drives.append(drive["id"])
                        search_url = f"https://graph.microsoft.com/v1.0/drives/{drive['id']}/search(q='{query}')"
                        search_res = requests.get(search_url, headers=headers)
                        if search_res.status_code == 200:
                            all_results += tag_site_id(search_res.json().get("value", []), site_id)

            sites_url = sites_data.get("@odata.nextLink")
        else:
            break

    print("🔎 All Sites:", all_sites)
    print("📁 All Drives:", all_drives)
    print(f"✅ Found {len(all_results)} total files matching: '{query}'")

    # Fallback if nothing is found
    if not all_results:
        print("⚠️ No results from direct search. Trying fallback...")
        all_results += fetch_recent_files(token)

    return rank_files_by_similarity(query, all_results, top_k=5)


def fetch_recent_files(token):
    headers = {"Authorization": f"Bearer {token}"}
    files = []

    try:
        res = requests.get("https://graph.microsoft.com/v1.0/me/drive/recent", headers=headers)
        if res.status_code == 200:
            files += tag_site_id(res.json().get("value", []), "personal")
    except Exception as e:
        print("⚠️ Failed to fetch recent files:", e)

    return files


def tag_site_id(items, site_id):
    for item in items:
        if "parentReference" not in item:
            item["parentReference"] = {}
        item["parentReference"]["siteId"] = site_id
    return items


def check_file_access(token, item_id, user_email, site_id=None):
    headers = {"Authorization": f"Bearer {token}"}
    urls = [
        f"https://graph.microsoft.com/v1.0/me/drive/items/{item_id}/permissions",
        f"https://graph.microsoft.com/v1.0/users/{user_email}/drive/items/{item_id}/permissions"
    ]
    if site_id and site_id != "personal":
        urls.append(f"https://graph.microsoft.com/v1.0/sites/{site_id}/drive/items/{item_id}/permissions")

    for url in urls:
        try:
            res = requests.get(url, headers=headers)
            if res.status_code == 200:
                for p in res.json().get("value", []):
                    granted_to_list = p.get('grantedToIdentitiesV2', [])
                    email = (
                        p.get('grantedTo', {}).get('user', {}).get('email') or
                        (granted_to_list[0].get('user', {}).get('email') if granted_to_list else None) or
                        p.get('grantedToV2', {}).get('user', {}).get('email')
                    )
                    roles = p.get('roles', [])
                    if (email is None or email.lower() == user_email.lower()) and any(r.lower() in ["read", "view", "write"] for r in roles):
                        return True
        except Exception as e:
            print(f"⚠️ Permission check failed: {e}")
            continue
    return False


def send_notification_email(token, to_email, file_name, file_url):
    url = "https://graph.microsoft.com/v1.0/me/sendMail"
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json"
    }
    message = {
        "message": {
            "subject": f"Here is the file: {file_name}",
            "body": {
                "contentType": "HTML",
                "content": f"<p>You requested this file:</p><p><a href='{file_url}'>{file_name}</a></p>"
            },
            "toRecipients": [{"emailAddress": {"address": to_email}}]
        },
        "saveToSentItems": True
    }
    try:
        response = requests.post(url, headers=headers, json=message)
        return response.status_code == 202
    except Exception as e:
        print(f"❌ Email send failed: {e}")
        return False


def send_multiple_file_email(token, to_email, files):
    url = "https://graph.microsoft.com/v1.0/me/sendMail"
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json"
    }

    file_links_html = "".join(
        f"<p><a href='{file['webUrl']}'>{file['name']}</a></p>" for file in files
    )

    message = {
        "message": {
            "subject": "Your requested files",
            "body": {
                "contentType": "HTML",
                "content": f"<p>Here are the files you requested:</p>{file_links_html}"
            },
            "toRecipients": [{"emailAddress": {"address": to_email}}]
        },
        "saveToSentItems": True
    }

    try:
        response = requests.post(url, headers=headers, json=message)
        return response.status_code == 202
    except Exception as e:
        print(f"❌ Multi-file email failed: {e}")
        return False
