#!/usr/bin/env python3
"""
Backend API tests for NEW features (iteration #5):
- Block format import with emojis
- Background import jobs with polling
- Pagination + search
- Deletions (all, bulk, range)
- Export streaming (CSV, TXT)
- Emoji cleanup verification
"""

import os
import sys
import requests
import json
import time
from datetime import datetime

# Read backend URL from frontend/.env
with open('/app/frontend/.env', 'r') as f:
    for line in f:
        if line.startswith('REACT_APP_BACKEND_URL='):
            BACKEND_URL = line.split('=', 1)[1].strip()
            break

BASE_URL = f"{BACKEND_URL}/api"

# Admin credentials from /app/memory/test_credentials.md
ADMIN_EMAIL = "dacostakanan@gmail.com"
ADMIN_PASSWORD = "24689100?C"

# Test results tracking
tests_passed = 0
tests_failed = 0
failures = []

def log_test(name, passed, details=""):
    global tests_passed, tests_failed, failures
    if passed:
        tests_passed += 1
        print(f"✅ {name}")
    else:
        tests_failed += 1
        failures.append(f"{name}: {details}")
        print(f"❌ {name}")
        if details:
            print(f"   {details}")

def admin_login():
    """Login as admin and return cookies"""
    print("\n=== Admin Login ===")
    resp = requests.post(f"{BASE_URL}/auth/login", json={
        "email": ADMIN_EMAIL,
        "password": ADMIN_PASSWORD
    })
    log_test("Admin login with correct password", 
             resp.status_code == 200, 
             f"Got {resp.status_code}: {resp.text}")
    
    if resp.status_code != 200:
        return None
    
    user = resp.json().get("user", {})
    log_test("Admin user.role='admin'", 
             user.get("role") == "admin",
             f"Got role={user.get('role')}")
    
    # Test wrong password
    resp = requests.post(f"{BASE_URL}/auth/login", json={
        "email": ADMIN_EMAIL,
        "password": "wrongpassword"
    })
    log_test("Admin login with wrong password returns 401",
             resp.status_code == 401,
             f"Got {resp.status_code}")
    
    return requests.post(f"{BASE_URL}/auth/login", json={
        "email": ADMIN_EMAIL,
        "password": ADMIN_PASSWORD
    }).cookies

def test_pagination_search(admin_cookies):
    """Test 1: Pagination + search"""
    print("\n=== Test 1: Pagination + Search ===")
    
    # 1.1: GET /api/admin/profiles without auth
    resp = requests.get(f"{BASE_URL}/admin/profiles")
    log_test("1.1: GET /api/admin/profiles without cookie returns 401",
             resp.status_code == 401,
             f"Got {resp.status_code}")
    
    # 1.2: GET /api/admin/profiles with admin cookie
    resp = requests.get(f"{BASE_URL}/admin/profiles?skip=0&limit=50&q=", cookies=admin_cookies)
    log_test("1.2: GET /api/admin/profiles with admin cookie returns 200",
             resp.status_code == 200,
             f"Got {resp.status_code}: {resp.text}")
    
    if resp.status_code == 200:
        data = resp.json()
        log_test("1.3: Response has profiles, total, skip, limit fields",
                 "profiles" in data and "total" in data and "skip" in data and "limit" in data,
                 f"Got keys: {list(data.keys())}")
        
        log_test("1.4: skip=0, limit=50",
                 data.get("skip") == 0 and data.get("limit") == 50,
                 f"Got skip={data.get('skip')}, limit={data.get('limit')}")
    
    # 1.5: Test with non-admin user (should return 403)
    # First create a profile and login
    resp = requests.post(f"{BASE_URL}/admin/profiles",
                        cookies=admin_cookies,
                        json={
                            "email": "testuser@test.fr",
                            "phone": "0699999999",
                            "name": "Test User",
                            "iban_last4": "1111"
                        })
    if resp.status_code == 200:
        # Login as profile user
        profile_resp = requests.post(f"{BASE_URL}/auth/login", json={
            "email": "testuser@test.fr",
            "password": "anything"
        })
        if profile_resp.status_code == 200:
            profile_cookies = profile_resp.cookies
            resp = requests.get(f"{BASE_URL}/admin/profiles", cookies=profile_cookies)
            log_test("1.5: GET /api/admin/profiles with non-admin session returns 403",
                     resp.status_code == 403,
                     f"Got {resp.status_code}")

def test_block_import_with_emojis(admin_cookies):
    """Test 2: Block format import with emojis (MAIN FEATURE)"""
    print("\n=== Test 2: Block Format Import with Emojis (MAIN FEATURE) ===")
    
    # Clear all profiles first
    resp = requests.delete(f"{BASE_URL}/admin/profiles/all", cookies=admin_cookies)
    print(f"Cleared all profiles: {resp.status_code}")
    
    # 2.1: Import BLOCK format with emojis
    block_text = """── #1 ──
👤 DEFOSSE YOANNE
📧 ydefosse@hotmail.com
📱 0652127810
🏠 13 IMPASSE DE L HAUNAY
📮 28260 SAUSSAY
📅 Né(e) en 1979
── #2 ──
👤 CANALES ALICIA
📧 alicia.pousson@live.fr
📱 0615102087
🏠 5 COTE SAINT JEAN
📮 28260 SAUSSAY
📅 Né(e) en 1985"""
    
    resp = requests.post(f"{BASE_URL}/admin/profiles/import",
                        cookies=admin_cookies,
                        json={"text": block_text})
    log_test("2.1: POST /api/admin/profiles/import with BLOCK format returns 200",
             resp.status_code == 200,
             f"Got {resp.status_code}: {resp.text}")
    
    job_id = None
    if resp.status_code == 200:
        job_id = resp.json().get("job_id")
        log_test("2.2: Import returns job_id",
                 job_id is not None,
                 f"Got job_id: {job_id}")
    
    # 2.3: Poll import status until done
    if job_id:
        max_polls = 30
        poll_count = 0
        status = None
        
        while poll_count < max_polls:
            resp = requests.get(f"{BASE_URL}/admin/profiles/import-status/{job_id}",
                              cookies=admin_cookies)
            if resp.status_code == 200:
                status_data = resp.json()
                status = status_data.get("status")
                
                if status == "done":
                    log_test("2.3: Import job status reaches 'done'",
                             True, "")
                    
                    created = status_data.get("created", 0)
                    log_test("2.4: Import created=2 profiles",
                             created == 2,
                             f"Got created={created}, status_data={status_data}")
                    break
                elif status == "error":
                    log_test("2.3: Import job status reaches 'done'",
                             False,
                             f"Job failed with error: {status_data.get('message')}")
                    break
            
            time.sleep(0.5)
            poll_count += 1
        
        if poll_count >= max_polls:
            log_test("2.3: Import job status reaches 'done'",
                     False,
                     f"Timeout after {max_polls} polls, last status: {status}")
    
    # 2.5: Verify profiles have NO emojis in stored values
    resp = requests.get(f"{BASE_URL}/admin/profiles", cookies=admin_cookies)
    if resp.status_code == 200:
        profiles = resp.json().get("profiles", [])
        
        # Find DEFOSSE YOANNE
        defosse = next((p for p in profiles if "DEFOSSE" in p.get("name", "")), None)
        if defosse:
            name = defosse.get("name", "")
            email = defosse.get("email", "")
            phone = defosse.get("phone", "")
            address = defosse.get("address", "")
            postal_code = defosse.get("postal_code", "")
            city = defosse.get("city", "")
            birth_year = defosse.get("birth_year", "")
            
            # Check NO emojis in any field
            has_emoji = any(ord(c) > 0x1F000 for field in [name, email, phone, address, city, birth_year] for c in field)
            
            log_test("2.5: DEFOSSE profile has NO emojis in any field",
                     not has_emoji,
                     f"name={name}, email={email}, phone={phone}, address={address}, postal_code={postal_code}, city={city}, birth_year={birth_year}")
            
            log_test("2.6: DEFOSSE name='DEFOSSE YOANNE' (no emoji)",
                     name == "DEFOSSE YOANNE",
                     f"Got name='{name}'")
            
            log_test("2.7: DEFOSSE email='ydefosse@hotmail.com'",
                     email == "ydefosse@hotmail.com",
                     f"Got email='{email}'")
            
            log_test("2.8: DEFOSSE phone='0652127810'",
                     phone == "0652127810",
                     f"Got phone='{phone}'")
            
            log_test("2.9: DEFOSSE address='13 IMPASSE DE L HAUNAY'",
                     address == "13 IMPASSE DE L HAUNAY",
                     f"Got address='{address}'")
            
            log_test("2.10: DEFOSSE postal_code='28260'",
                     postal_code == "28260",
                     f"Got postal_code='{postal_code}'")
            
            log_test("2.11: DEFOSSE city='SAUSSAY'",
                     city == "SAUSSAY",
                     f"Got city='{city}'")
            
            log_test("2.12: DEFOSSE birth_year='1979'",
                     birth_year == "1979",
                     f"Got birth_year='{birth_year}'")
        else:
            log_test("2.5: DEFOSSE profile found",
                     False,
                     f"DEFOSSE not found in profiles: {[p.get('name') for p in profiles]}")
        
        # Find CANALES ALICIA
        canales = next((p for p in profiles if "CANALES" in p.get("name", "")), None)
        if canales:
            name = canales.get("name", "")
            email = canales.get("email", "")
            birth_year = canales.get("birth_year", "")
            
            log_test("2.13: CANALES name='CANALES ALICIA' (no emoji)",
                     name == "CANALES ALICIA",
                     f"Got name='{name}'")
            
            log_test("2.14: CANALES email='alicia.pousson@live.fr'",
                     email == "alicia.pousson@live.fr",
                     f"Got email='{email}'")
            
            log_test("2.15: CANALES birth_year='1985'",
                     birth_year == "1985",
                     f"Got birth_year='{birth_year}'")

def test_horizontal_csv_import(admin_cookies):
    """Test 3: Horizontal CSV import still works"""
    print("\n=== Test 3: Horizontal CSV Import ===")
    
    csv_text = "email,phone,name,iban_last4\njean@test.fr,0611112222,Jean DUPONT,1234"
    
    resp = requests.post(f"{BASE_URL}/admin/profiles/import",
                        cookies=admin_cookies,
                        json={"text": csv_text})
    log_test("3.1: POST /api/admin/profiles/import with CSV returns 200",
             resp.status_code == 200,
             f"Got {resp.status_code}: {resp.text}")
    
    job_id = None
    if resp.status_code == 200:
        job_id = resp.json().get("job_id")
    
    # Poll until done
    if job_id:
        max_polls = 30
        poll_count = 0
        
        while poll_count < max_polls:
            resp = requests.get(f"{BASE_URL}/admin/profiles/import-status/{job_id}",
                              cookies=admin_cookies)
            if resp.status_code == 200:
                status_data = resp.json()
                status = status_data.get("status")
                
                if status == "done":
                    created = status_data.get("created", 0)
                    log_test("3.2: CSV import created >= 1 profile",
                             created >= 1,
                             f"Got created={created}")
                    break
                elif status == "error":
                    log_test("3.2: CSV import succeeded",
                             False,
                             f"Job failed: {status_data.get('message')}")
                    break
            
            time.sleep(0.5)
            poll_count += 1

def test_dedup(admin_cookies):
    """Test 4: Deduplication - two records with same email"""
    print("\n=== Test 4: Deduplication ===")
    
    # Clear all profiles first
    resp = requests.delete(f"{BASE_URL}/admin/profiles/all", cookies=admin_cookies)
    print(f"Cleared all profiles: {resp.status_code}")
    
    # Import block text with two records sharing the same email
    dup_text = """── #1 ──
👤 DUPONT JEAN
📧 duplicate@test.fr
📱 0611111111
🏠 1 RUE DE LA PAIX
📮 75001 PARIS
📅 Né(e) en 1980
── #2 ──
👤 DUPONT MARIE
📧 duplicate@test.fr
📱 0622222222
🏠 2 RUE DE LA PAIX
📮 75002 PARIS
📅 Né(e) en 1985"""
    
    resp = requests.post(f"{BASE_URL}/admin/profiles/import",
                        cookies=admin_cookies,
                        json={"text": dup_text})
    log_test("4.1: POST import with duplicate email returns 200",
             resp.status_code == 200,
             f"Got {resp.status_code}")
    
    job_id = None
    if resp.status_code == 200:
        job_id = resp.json().get("job_id")
    
    # Poll until done
    if job_id:
        max_polls = 30
        poll_count = 0
        
        while poll_count < max_polls:
            resp = requests.get(f"{BASE_URL}/admin/profiles/import-status/{job_id}",
                              cookies=admin_cookies)
            if resp.status_code == 200:
                status_data = resp.json()
                status = status_data.get("status")
                
                if status == "done":
                    created = status_data.get("created", 0)
                    updated = status_data.get("updated", 0)
                    
                    log_test("4.2: Dedup: created + updated reflects dedup",
                             True,
                             f"created={created}, updated={updated}")
                    break
                elif status == "error":
                    log_test("4.2: Dedup import succeeded",
                             False,
                             f"Job failed: {status_data.get('message')}")
                    break
            
            time.sleep(0.5)
            poll_count += 1
    
    # 4.3: Verify only ONE profile exists for duplicate@test.fr
    resp = requests.get(f"{BASE_URL}/admin/profiles", cookies=admin_cookies)
    if resp.status_code == 200:
        profiles = resp.json().get("profiles", [])
        dup_profiles = [p for p in profiles if p.get("email") == "duplicate@test.fr"]
        
        log_test("4.3: Only ONE profile exists for duplicate@test.fr",
                 len(dup_profiles) == 1,
                 f"Found {len(dup_profiles)} profiles with duplicate@test.fr")
        
        if len(dup_profiles) == 1:
            # Should have the LAST record's data (MARIE)
            profile = dup_profiles[0]
            log_test("4.4: Dedup kept last record (DUPONT MARIE)",
                     "MARIE" in profile.get("name", ""),
                     f"Got name: {profile.get('name')}")

def test_import_file(admin_cookies):
    """Test 5: Import file (multipart)"""
    print("\n=== Test 5: Import File (multipart) ===")
    
    # Create a temporary file with block format
    file_content = """── #1 ──
👤 MARTIN SOPHIE
📧 sophie.martin@test.fr
📱 0633333333
🏠 10 AVENUE DES CHAMPS
📮 75008 PARIS
📅 Né(e) en 1990"""
    
    files = {'file': ('test_import.txt', file_content, 'text/plain')}
    
    resp = requests.post(f"{BASE_URL}/admin/profiles/import-file",
                        cookies=admin_cookies,
                        files=files)
    log_test("5.1: POST /api/admin/profiles/import-file returns 200",
             resp.status_code == 200,
             f"Got {resp.status_code}: {resp.text}")
    
    job_id = None
    if resp.status_code == 200:
        job_id = resp.json().get("job_id")
    
    # Poll until done
    if job_id:
        max_polls = 30
        poll_count = 0
        
        while poll_count < max_polls:
            resp = requests.get(f"{BASE_URL}/admin/profiles/import-status/{job_id}",
                              cookies=admin_cookies)
            if resp.status_code == 200:
                status_data = resp.json()
                status = status_data.get("status")
                
                if status == "done":
                    log_test("5.2: Import-file job reaches 'done'",
                             True, "")
                    break
                elif status == "error":
                    log_test("5.2: Import-file job succeeded",
                             False,
                             f"Job failed: {status_data.get('message')}")
                    break
            
            time.sleep(0.5)
            poll_count += 1

def test_deletions(admin_cookies):
    """Test 6: Deletions (bulk, range, all)"""
    print("\n=== Test 6: Deletions ===")
    
    # First, ensure we have some profiles
    resp = requests.get(f"{BASE_URL}/admin/profiles", cookies=admin_cookies)
    if resp.status_code == 200:
        profiles = resp.json().get("profiles", [])
        print(f"Current profiles count: {len(profiles)}")
        
        if len(profiles) >= 2:
            # 6.1: Test delete-bulk
            ids_to_delete = [profiles[0].get("id"), profiles[1].get("id")]
            resp = requests.post(f"{BASE_URL}/admin/profiles/delete-bulk",
                               cookies=admin_cookies,
                               json={"ids": ids_to_delete})
            log_test("6.1: POST /api/admin/profiles/delete-bulk returns 200",
                     resp.status_code == 200,
                     f"Got {resp.status_code}: {resp.text}")
            
            if resp.status_code == 200:
                deleted = resp.json().get("deleted", 0)
                log_test("6.2: delete-bulk deleted=2",
                         deleted == 2,
                         f"Got deleted={deleted}")
        
        # 6.3: Test delete-range
        resp = requests.post(f"{BASE_URL}/admin/profiles/delete-range",
                           cookies=admin_cookies,
                           json={"start": 1, "end": 1})
        log_test("6.3: POST /api/admin/profiles/delete-range returns 200",
                 resp.status_code == 200,
                 f"Got {resp.status_code}: {resp.text}")
        
        if resp.status_code == 200:
            deleted = resp.json().get("deleted", 0)
            log_test("6.4: delete-range deleted=1",
                     deleted == 1,
                     f"Got deleted={deleted}")
    
    # 6.5: Test delete-all
    resp = requests.delete(f"{BASE_URL}/admin/profiles/all", cookies=admin_cookies)
    log_test("6.5: DELETE /api/admin/profiles/all returns 200",
             resp.status_code == 200,
             f"Got {resp.status_code}: {resp.text}")
    
    # 6.6: Verify total=0 after delete-all
    resp = requests.get(f"{BASE_URL}/admin/profiles", cookies=admin_cookies)
    if resp.status_code == 200:
        total = resp.json().get("total", -1)
        log_test("6.6: After delete-all, total=0",
                 total == 0,
                 f"Got total={total}")
    
    # 6.7: Test delete-bulk with non-admin session (should return 403)
    # Create a profile and login
    resp = requests.post(f"{BASE_URL}/admin/profiles",
                        cookies=admin_cookies,
                        json={
                            "email": "testuser2@test.fr",
                            "phone": "0688888888",
                            "name": "Test User 2",
                            "iban_last4": "2222"
                        })
    if resp.status_code == 200:
        profile_resp = requests.post(f"{BASE_URL}/auth/login", json={
            "email": "testuser2@test.fr",
            "password": "anything"
        })
        if profile_resp.status_code == 200:
            profile_cookies = profile_resp.cookies
            
            resp = requests.post(f"{BASE_URL}/admin/profiles/delete-bulk",
                               cookies=profile_cookies,
                               json={"ids": ["507f1f77bcf86cd799439011"]})
            log_test("6.7: delete-bulk with non-admin session returns 403",
                     resp.status_code == 403,
                     f"Got {resp.status_code}")
            
            resp = requests.post(f"{BASE_URL}/admin/profiles/delete-range",
                               cookies=profile_cookies,
                               json={"start": 1, "end": 1})
            log_test("6.8: delete-range with non-admin session returns 403",
                     resp.status_code == 403,
                     f"Got {resp.status_code}")
            
            resp = requests.delete(f"{BASE_URL}/admin/profiles/all",
                                 cookies=profile_cookies)
            log_test("6.9: delete-all with non-admin session returns 403",
                     resp.status_code == 403,
                     f"Got {resp.status_code}")
    
    # 6.10: Test without auth
    resp = requests.delete(f"{BASE_URL}/admin/profiles/all")
    log_test("6.10: delete-all without auth returns 401",
             resp.status_code == 401,
             f"Got {resp.status_code}")

def test_export_streaming(admin_cookies):
    """Test 7: Export streaming (CSV, TXT)"""
    print("\n=== Test 7: Export Streaming ===")
    
    # First, seed at least 1 profile
    resp = requests.post(f"{BASE_URL}/admin/profiles",
                        cookies=admin_cookies,
                        json={
                            "email": "export@test.fr",
                            "phone": "0677777777",
                            "name": "Export Test",
                            "iban_last4": "7777",
                            "address": "123 Export Street",
                            "postal_code": "75001",
                            "city": "Paris",
                            "birth_year": "1990"
                        })
    print(f"Seeded profile for export: {resp.status_code}")
    
    # 7.1: Export CSV
    resp = requests.get(f"{BASE_URL}/admin/profiles/export?format=csv",
                       cookies=admin_cookies)
    log_test("7.1: GET /api/admin/profiles/export?format=csv returns 200",
             resp.status_code == 200,
             f"Got {resp.status_code}")
    
    if resp.status_code == 200:
        content_type = resp.headers.get("Content-Type", "")
        log_test("7.2: CSV export Content-Type is text/csv",
                 "text/csv" in content_type,
                 f"Got Content-Type: {content_type}")
        
        content_disp = resp.headers.get("Content-Disposition", "")
        log_test("7.3: CSV export has Content-Disposition attachment",
                 "attachment" in content_disp,
                 f"Got Content-Disposition: {content_disp}")
        
        # Check CSV has header row
        csv_content = resp.text
        log_test("7.4: CSV has header row with required columns",
                 "name,email,phone,address,postal_code,city,birth_year,iban_last4,bic,bank_name" in csv_content,
                 f"First 200 chars: {csv_content[:200]}")
    
    # 7.5: Export TXT
    resp = requests.get(f"{BASE_URL}/admin/profiles/export?format=txt",
                       cookies=admin_cookies)
    log_test("7.5: GET /api/admin/profiles/export?format=txt returns 200",
             resp.status_code == 200,
             f"Got {resp.status_code}")
    
    if resp.status_code == 200:
        content_type = resp.headers.get("Content-Type", "")
        log_test("7.6: TXT export Content-Type is text/plain",
                 "text/plain" in content_type,
                 f"Got Content-Type: {content_type}")
        
        content_disp = resp.headers.get("Content-Disposition", "")
        log_test("7.7: TXT export has Content-Disposition attachment",
                 "attachment" in content_disp,
                 f"Got Content-Disposition: {content_disp}")

def test_profile_login_emoji_cleanup(admin_cookies):
    """Test 8: Profile login + /api/auth/me with emoji cleanup"""
    print("\n=== Test 8: Profile Login + /api/auth/me (emoji cleanup) ===")
    
    # Import a profile with emojis
    block_text = """── #1 ──
👤 BERNARD CLAIRE
📧 claire.bernard@test.fr
📱 0644444444
🏠 5 RUE DU TEST
📮 69001 LYON
📅 Né(e) en 1988"""
    
    resp = requests.post(f"{BASE_URL}/admin/profiles/import",
                        cookies=admin_cookies,
                        json={"text": block_text})
    
    if resp.status_code == 200:
        job_id = resp.json().get("job_id")
        
        # Poll until done
        max_polls = 30
        poll_count = 0
        
        while poll_count < max_polls:
            resp = requests.get(f"{BASE_URL}/admin/profiles/import-status/{job_id}",
                              cookies=admin_cookies)
            if resp.status_code == 200:
                status = resp.json().get("status")
                if status in ["done", "error"]:
                    break
            time.sleep(0.5)
            poll_count += 1
    
    # 8.1: Login with email
    resp = requests.post(f"{BASE_URL}/auth/login", json={
        "email": "claire.bernard@test.fr",
        "password": "anything"
    })
    log_test("8.1: Profile login with email returns 200",
             resp.status_code == 200,
             f"Got {resp.status_code}")
    
    profile_cookies = None
    if resp.status_code == 200:
        profile_cookies = resp.cookies
    
    # 8.2: GET /api/auth/me
    if profile_cookies:
        resp = requests.get(f"{BASE_URL}/auth/me", cookies=profile_cookies)
        log_test("8.2: GET /api/auth/me returns 200",
                 resp.status_code == 200,
                 f"Got {resp.status_code}")
        
        if resp.status_code == 200:
            user = resp.json().get("user", {})
            name = user.get("name", "")
            address = user.get("address", "")
            city = user.get("city", "")
            birth_year = user.get("birth_year", "")
            iban_masked = user.get("iban_masked", "")
            
            # Check NO emojis in any field
            has_emoji = any(ord(c) > 0x1F000 for field in [name, address, city, birth_year] for c in field)
            
            log_test("8.3: /api/auth/me returns data WITHOUT emojis",
                     not has_emoji,
                     f"name={name}, address={address}, city={city}, birth_year={birth_year}")
            
            log_test("8.4: name='BERNARD CLAIRE' (no emoji)",
                     name == "BERNARD CLAIRE",
                     f"Got name='{name}'")
            
            log_test("8.5: address='5 RUE DU TEST' (no emoji)",
                     address == "5 RUE DU TEST",
                     f"Got address='{address}'")
            
            log_test("8.6: city='LYON' (no emoji)",
                     city == "LYON",
                     f"Got city='{city}'")
            
            log_test("8.7: birth_year='1988' (no emoji)",
                     birth_year == "1988",
                     f"Got birth_year='{birth_year}'")
            
            log_test("8.8: iban_masked is present",
                     iban_masked != "",
                     f"Got iban_masked='{iban_masked}'")
    
    # 8.9: Login with phone
    resp = requests.post(f"{BASE_URL}/auth/login", json={
        "email": "0644444444",
        "password": "anything"
    })
    log_test("8.9: Profile login with phone returns 200",
             resp.status_code == 200,
             f"Got {resp.status_code}")

def main():
    print(f"Backend URL: {BASE_URL}")
    print(f"Admin credentials: {ADMIN_EMAIL} / {ADMIN_PASSWORD}")
    print("=" * 80)
    
    # Admin login
    admin_cookies = admin_login()
    
    if not admin_cookies:
        print("\n❌ CRITICAL: Admin authentication failed. Cannot continue.")
        return 1
    
    # Run all tests
    test_pagination_search(admin_cookies)
    test_block_import_with_emojis(admin_cookies)
    test_horizontal_csv_import(admin_cookies)
    test_dedup(admin_cookies)
    test_import_file(admin_cookies)
    test_deletions(admin_cookies)
    test_export_streaming(admin_cookies)
    test_profile_login_emoji_cleanup(admin_cookies)
    
    # Summary
    print("\n" + "=" * 80)
    print(f"TESTS PASSED: {tests_passed}")
    print(f"TESTS FAILED: {tests_failed}")
    
    if failures:
        print("\n❌ FAILURES:")
        for failure in failures:
            print(f"  - {failure}")
    
    print("=" * 80)
    
    return 0 if tests_failed == 0 else 1

if __name__ == "__main__":
    sys.exit(main())
