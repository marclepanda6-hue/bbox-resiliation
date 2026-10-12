#!/usr/bin/env python3
"""
Backend API tests for overhauled authentication and admin flow.
Tests admin auth, profile CRUD, bulk import, subscription flow, and removed endpoints.
"""

import os
import sys
import requests
import json
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

def wipe_customer_profiles(admin_cookies):
    """Wipe all customer_profiles before testing"""
    print("\n=== Wiping customer_profiles collection ===")
    resp = requests.get(f"{BASE_URL}/admin/profiles", cookies=admin_cookies)
    if resp.status_code == 200:
        profiles = resp.json().get("profiles", [])
        print(f"Found {len(profiles)} profiles to delete")
        for profile in profiles:
            profile_id = profile.get("id")
            if profile_id:
                del_resp = requests.delete(f"{BASE_URL}/admin/profiles/{profile_id}", cookies=admin_cookies)
                if del_resp.status_code == 200:
                    print(f"  Deleted profile {profile_id}")
                else:
                    print(f"  Failed to delete profile {profile_id}: {del_resp.status_code}")
        print("✅ customer_profiles collection wiped")
    else:
        print(f"⚠️  Could not fetch profiles: {resp.status_code}")

def test_admin_auth():
    """Test 1: Admin authentication"""
    print("\n=== Test 1: Admin Authentication ===")
    
    # 1.1: Login with correct admin credentials
    resp = requests.post(f"{BASE_URL}/auth/login", json={
        "email": ADMIN_EMAIL,
        "password": ADMIN_PASSWORD
    })
    log_test("1.1: Admin login with correct password returns 200", 
             resp.status_code == 200, 
             f"Got {resp.status_code}: {resp.text}")
    
    if resp.status_code != 200:
        return None
    
    admin_cookies = resp.cookies
    data = resp.json()
    user = data.get("user", {})
    
    log_test("1.2: Admin user.role='admin'", 
             user.get("role") == "admin",
             f"Got role={user.get('role')}")
    
    log_test("1.3: Admin user.kind='user'",
             user.get("kind") == "user",
             f"Got kind={user.get('kind')}")
    
    # 1.4: Login with admin email + WRONG password
    resp = requests.post(f"{BASE_URL}/auth/login", json={
        "email": ADMIN_EMAIL,
        "password": "wrongpassword123"
    })
    log_test("1.4: Admin login with wrong password returns 401",
             resp.status_code == 401,
             f"Got {resp.status_code}: {resp.text}")
    
    if resp.status_code == 401:
        log_test("1.5: Wrong password error message is 'Identifiant ou mot de passe incorrect.'",
                 "Identifiant ou mot de passe incorrect" in resp.text,
                 f"Got message: {resp.text}")
    
    # 1.6: GET /api/admin/profiles with admin cookie
    resp = requests.get(f"{BASE_URL}/admin/profiles", cookies=admin_cookies)
    log_test("1.6: GET /api/admin/profiles with admin cookie returns 200",
             resp.status_code == 200,
             f"Got {resp.status_code}: {resp.text}")
    
    # 1.7: GET /api/admin/profiles without cookie
    resp = requests.get(f"{BASE_URL}/admin/profiles")
    log_test("1.7: GET /api/admin/profiles without cookie returns 401",
             resp.status_code == 401,
             f"Got {resp.status_code}: {resp.text}")
    
    return admin_cookies

def test_admin_crud(admin_cookies):
    """Test 2: Admin CRUD on /api/admin/profiles"""
    print("\n=== Test 2: Admin CRUD on /api/admin/profiles ===")
    
    if not admin_cookies:
        print("⚠️  Skipping CRUD tests - no admin cookies")
        return None
    
    # 2.1: POST with valid data
    resp = requests.post(f"{BASE_URL}/admin/profiles", 
                        cookies=admin_cookies,
                        json={
                            "email": "vincentmarie@gmail.com",
                            "phone": "0612345678",
                            "name": "Vincent MARIE",
                            "iban_last4": "4521"
                        })
    log_test("2.1: POST profile with email+phone+name+iban returns 200",
             resp.status_code == 200,
             f"Got {resp.status_code}: {resp.text}")
    
    profile1_id = None
    if resp.status_code == 200:
        profile1_id = resp.json().get("profile", {}).get("id")
    
    # 2.2: POST without email AND without phone
    resp = requests.post(f"{BASE_URL}/admin/profiles",
                        cookies=admin_cookies,
                        json={
                            "name": "No Contact",
                            "iban_last4": "1234"
                        })
    log_test("2.2: POST without email AND without phone returns 400",
             resp.status_code == 400,
             f"Got {resp.status_code}: {resp.text}")
    
    if resp.status_code == 400:
        log_test("2.3: Error message contains 'Email ou téléphone obligatoire'",
                 "Email ou téléphone obligatoire" in resp.text,
                 f"Got: {resp.text}")
    
    # 2.4: POST with invalid email
    resp = requests.post(f"{BASE_URL}/admin/profiles",
                        cookies=admin_cookies,
                        json={
                            "email": "not-an-email",
                            "name": "Invalid Email",
                            "iban_last4": "1234"
                        })
    log_test("2.4: POST with invalid email 'not-an-email' returns 400",
             resp.status_code == 400,
             f"Got {resp.status_code}: {resp.text}")
    
    if resp.status_code == 400:
        log_test("2.5: Error message contains 'Email invalide'",
                 "Email invalide" in resp.text,
                 f"Got: {resp.text}")
    
    # 2.6: POST with iban_last4="12" (only 2 digits)
    resp = requests.post(f"{BASE_URL}/admin/profiles",
                        cookies=admin_cookies,
                        json={
                            "email": "test2digits@test.fr",
                            "name": "Two Digits",
                            "iban_last4": "12"
                        })
    log_test("2.6: POST with iban_last4='12' (2 digits) returns 400",
             resp.status_code == 400,
             f"Got {resp.status_code}: {resp.text}")
    
    # 2.7: POST with iban_last4="" and only phone
    resp = requests.post(f"{BASE_URL}/admin/profiles",
                        cookies=admin_cookies,
                        json={
                            "phone": "0698765432",
                            "name": "Phone Only",
                            "iban_last4": ""
                        })
    log_test("2.7: POST with iban_last4='' and only phone returns 200",
             resp.status_code == 200,
             f"Got {resp.status_code}: {resp.text}")
    
    profile2_id = None
    if resp.status_code == 200:
        profile2_id = resp.json().get("profile", {}).get("id")
    
    # 2.8: POST duplicate email
    resp = requests.post(f"{BASE_URL}/admin/profiles",
                        cookies=admin_cookies,
                        json={
                            "email": "vincentmarie@gmail.com",
                            "name": "Duplicate Email",
                            "iban_last4": "9999"
                        })
    log_test("2.8: POST duplicate email returns 400",
             resp.status_code == 400,
             f"Got {resp.status_code}: {resp.text}")
    
    if resp.status_code == 400:
        log_test("2.9: Duplicate email error contains 'existe déjà'",
                 "existe déjà" in resp.text,
                 f"Got: {resp.text}")
    
    # 2.10: POST duplicate phone
    resp = requests.post(f"{BASE_URL}/admin/profiles",
                        cookies=admin_cookies,
                        json={
                            "phone": "0698765432",
                            "name": "Duplicate Phone",
                            "iban_last4": "8888"
                        })
    log_test("2.10: POST duplicate phone returns 400",
             resp.status_code == 400,
             f"Got {resp.status_code}: {resp.text}")
    
    if resp.status_code == 400:
        log_test("2.11: Duplicate phone error contains 'existe déjà'",
                 "existe déjà" in resp.text,
                 f"Got: {resp.text}")
    
    # 2.12: PUT to change name
    if profile1_id:
        resp = requests.put(f"{BASE_URL}/admin/profiles/{profile1_id}",
                           cookies=admin_cookies,
                           json={
                               "email": "vincentmarie@gmail.com",
                               "phone": "0612345678",
                               "name": "Vincent MARIE-UPDATED",
                               "iban_last4": "4521"
                           })
        log_test("2.12: PUT to change name returns 200",
                 resp.status_code == 200,
                 f"Got {resp.status_code}: {resp.text}")
        
        if resp.status_code == 200:
            updated = resp.json().get("profile", {})
            log_test("2.13: Updated profile has new name",
                     updated.get("name") == "Vincent MARIE-UPDATED",
                     f"Got name: {updated.get('name')}")
    
    # 2.14: PUT with invalid ObjectId
    resp = requests.put(f"{BASE_URL}/admin/profiles/invalid_id",
                       cookies=admin_cookies,
                       json={
                           "email": "test@test.fr",
                           "name": "Test",
                           "iban_last4": "1234"
                       })
    log_test("2.14: PUT with invalid ObjectId returns 400",
             resp.status_code == 400,
             f"Got {resp.status_code}: {resp.text}")
    
    # 2.15: PUT to non-existing id
    resp = requests.put(f"{BASE_URL}/admin/profiles/507f1f77bcf86cd799439011",
                       cookies=admin_cookies,
                       json={
                           "email": "nonexisting@test.fr",
                           "name": "Non Existing",
                           "iban_last4": "1234"
                       })
    log_test("2.15: PUT to non-existing id returns 404",
             resp.status_code == 404,
             f"Got {resp.status_code}: {resp.text}")
    
    # 2.16: DELETE profile
    if profile1_id:
        resp = requests.delete(f"{BASE_URL}/admin/profiles/{profile1_id}",
                              cookies=admin_cookies)
        log_test("2.16: DELETE profile returns 200",
                 resp.status_code == 200,
                 f"Got {resp.status_code}: {resp.text}")
        
        # 2.17: DELETE again
        resp = requests.delete(f"{BASE_URL}/admin/profiles/{profile1_id}",
                              cookies=admin_cookies)
        log_test("2.17: DELETE same profile again returns 404",
                 resp.status_code == 404,
                 f"Got {resp.status_code}: {resp.text}")
    
    # Clean up profile2
    if profile2_id:
        requests.delete(f"{BASE_URL}/admin/profiles/{profile2_id}", cookies=admin_cookies)
    
    return True

def test_profile_login(admin_cookies):
    """Test 3: Profile login (any password accepted)"""
    print("\n=== Test 3: Profile Login (any password accepted) ===")
    
    if not admin_cookies:
        print("⚠️  Skipping profile login tests - no admin cookies")
        return None
    
    # Create profile with email and phone
    resp = requests.post(f"{BASE_URL}/admin/profiles",
                        cookies=admin_cookies,
                        json={
                            "email": "alice@test.fr",
                            "phone": "0611111111",
                            "name": "Alice MARTIN",
                            "iban_last4": "1234"
                        })
    log_test("3.1: Create profile alice@test.fr returns 200",
             resp.status_code == 200,
             f"Got {resp.status_code}: {resp.text}")
    
    alice_id = None
    if resp.status_code == 200:
        alice_id = resp.json().get("profile", {}).get("id")
    
    # 3.2: Login with email + any password
    resp = requests.post(f"{BASE_URL}/auth/login", json={
        "email": "alice@test.fr",
        "password": "anything"
    })
    log_test("3.2: Login with email 'alice@test.fr' + password 'anything' returns 200",
             resp.status_code == 200,
             f"Got {resp.status_code}: {resp.text}")
    
    alice_cookies = None
    if resp.status_code == 200:
        alice_cookies = resp.cookies
        user = resp.json().get("user", {})
        
        log_test("3.3: user.name='Alice MARTIN'",
                 user.get("name") == "Alice MARTIN",
                 f"Got name: {user.get('name')}")
        
        log_test("3.4: user.iban_masked='•••• •••• •••• 1234'",
                 user.get("iban_masked") == "•••• •••• •••• 1234",
                 f"Got iban_masked: {user.get('iban_masked')}")
        
        log_test("3.5: user.kind='profile'",
                 user.get("kind") == "profile",
                 f"Got kind: {user.get('kind')}")
        
        log_test("3.6: user.role='user'",
                 user.get("role") == "user",
                 f"Got role: {user.get('role')}")
    
    # 3.7: Login with phone + different password
    resp = requests.post(f"{BASE_URL}/auth/login", json={
        "email": "0611111111",
        "password": "different"
    })
    log_test("3.7: Login with phone '0611111111' + password 'different' returns 200",
             resp.status_code == 200,
             f"Got {resp.status_code}: {resp.text}")
    
    if resp.status_code == 200:
        user = resp.json().get("user", {})
        log_test("3.8: Same user (Alice MARTIN) returned",
                 user.get("name") == "Alice MARTIN",
                 f"Got name: {user.get('name')}")
    
    # 3.9: Login with phone with spaces
    resp = requests.post(f"{BASE_URL}/auth/login", json={
        "email": "06 11 11 11 11",
        "password": "xxx"
    })
    log_test("3.9: Login with phone '06 11 11 11 11' (with spaces) returns 200",
             resp.status_code == 200,
             f"Got {resp.status_code}: {resp.text}")
    
    # 3.10: Login with phone +33 format
    resp = requests.post(f"{BASE_URL}/auth/login", json={
        "email": "+33611111111",
        "password": "xxx"
    })
    # This might be 200 or 401 depending on normalization - just report
    if resp.status_code == 200:
        log_test("3.10: Login with phone '+33611111111' returns 200 (normalization works)",
                 True, "")
    else:
        log_test("3.10: Login with phone '+33611111111' returns 401 (normalization doesn't match storage)",
                 resp.status_code == 401,
                 f"Got {resp.status_code}: {resp.text}")
    
    # 3.11: Login with unknown email
    resp = requests.post(f"{BASE_URL}/auth/login", json={
        "email": "unknown@test.fr",
        "password": "xxx"
    })
    log_test("3.11: Login with unknown email returns 401",
             resp.status_code == 401,
             f"Got {resp.status_code}: {resp.text}")
    
    if resp.status_code == 401:
        log_test("3.12: Unknown email error is 'Identifiant non autorisé.'",
                 "Identifiant non autorisé" in resp.text,
                 f"Got: {resp.text}")
    
    # 3.13: Login with unknown phone
    resp = requests.post(f"{BASE_URL}/auth/login", json={
        "email": "0699999999",
        "password": "xxx"
    })
    log_test("3.13: Login with unknown phone returns 401",
             resp.status_code == 401,
             f"Got {resp.status_code}: {resp.text}")
    
    if resp.status_code == 401:
        log_test("3.14: Unknown phone error is 'Identifiant non autorisé.'",
                 "Identifiant non autorisé" in resp.text,
                 f"Got: {resp.text}")
    
    # 3.15: GET /api/auth/me with alice's cookie
    if alice_cookies:
        resp = requests.get(f"{BASE_URL}/auth/me", cookies=alice_cookies)
        log_test("3.15: GET /api/auth/me with alice's cookie returns 200",
                 resp.status_code == 200,
                 f"Got {resp.status_code}: {resp.text}")
        
        if resp.status_code == 200:
            user = resp.json().get("user", {})
            log_test("3.16: /api/auth/me shows mapped data (name, iban_masked)",
                     user.get("name") == "Alice MARTIN" and user.get("iban_masked") == "•••• •••• •••• 1234",
                     f"Got user: {user}")
    
    return alice_id, alice_cookies

def test_non_admin_access(alice_cookies):
    """Test 4: Non-admin cannot access admin endpoints"""
    print("\n=== Test 4: Non-admin Cannot Access Admin Endpoints ===")
    
    if not alice_cookies:
        print("⚠️  Skipping non-admin access tests - no alice cookies")
        return
    
    # 4.1: GET /api/admin/profiles as alice
    resp = requests.get(f"{BASE_URL}/admin/profiles", cookies=alice_cookies)
    log_test("4.1: GET /api/admin/profiles as profile user returns 403",
             resp.status_code == 403,
             f"Got {resp.status_code}: {resp.text}")
    
    if resp.status_code == 403:
        log_test("4.2: 403 error is 'Accès réservé aux administrateurs.'",
                 "Accès réservé aux administrateurs" in resp.text,
                 f"Got: {resp.text}")
    
    # 4.3: POST /api/admin/profiles as alice
    resp = requests.post(f"{BASE_URL}/admin/profiles",
                        cookies=alice_cookies,
                        json={
                            "email": "test@test.fr",
                            "name": "Test",
                            "iban_last4": "1234"
                        })
    log_test("4.3: POST /api/admin/profiles as profile user returns 403",
             resp.status_code == 403,
             f"Got {resp.status_code}: {resp.text}")
    
    # 4.4: POST /api/admin/profiles/import as alice
    resp = requests.post(f"{BASE_URL}/admin/profiles/import",
                        cookies=alice_cookies,
                        json={"text": "email,phone,name,iban_last4\ntest@test.fr,0612345678,Test,1234"})
    log_test("4.4: POST /api/admin/profiles/import as profile user returns 403",
             resp.status_code == 403,
             f"Got {resp.status_code}: {resp.text}")

def test_bulk_import(admin_cookies):
    """Test 5: Bulk import"""
    print("\n=== Test 5: Bulk Import ===")
    
    if not admin_cookies:
        print("⚠️  Skipping bulk import tests - no admin cookies")
        return
    
    # 5.1: Import with mixed delimiters
    import_text = """email,phone,name,iban_last4
jean.dupont@example.com,0612000001,Jean DUPONT,1234
marie@test.fr;0612000002;Marie BERNARD;5678
bob@domain.com | 0612000003 | Bob BLANC | 9876
thomas@test.fr 0612000004 Thomas PETIT 3344
# comment ignored
alice@test.fr,0611111111,Alice ALICE,0000"""
    
    resp = requests.post(f"{BASE_URL}/admin/profiles/import",
                        cookies=admin_cookies,
                        json={"text": import_text})
    log_test("5.1: POST /api/admin/profiles/import with mixed delimiters returns 200",
             resp.status_code == 200,
             f"Got {resp.status_code}: {resp.text}")
    
    if resp.status_code == 200:
        result = resp.json()
        created = result.get("created", 0)
        updated = result.get("updated", 0)
        errors = result.get("errors", [])
        total = result.get("total", 0)
        
        log_test("5.2: Import result: 4 created, 1 updated, 0 errors, total 5",
                 created == 4 and updated == 1 and len(errors) == 0 and total == 5,
                 f"Got created={created}, updated={updated}, errors={len(errors)}, total={total}")
    
    # 5.3: Verify alice's profile was updated
    resp = requests.get(f"{BASE_URL}/admin/profiles", cookies=admin_cookies)
    if resp.status_code == 200:
        profiles = resp.json().get("profiles", [])
        alice = next((p for p in profiles if p.get("email") == "alice@test.fr"), None)
        
        if alice:
            log_test("5.3: Alice's iban_last4 updated to '0000'",
                     alice.get("iban_last4") == "0000",
                     f"Got iban_last4: {alice.get('iban_last4')}")
            
            log_test("5.4: Alice's name updated to 'Alice ALICE'",
                     alice.get("name") == "Alice ALICE",
                     f"Got name: {alice.get('name')}")
        else:
            log_test("5.3: Alice profile found after import", False, "Alice not found in profiles")
    
    # 5.5: Verify at least 5 profiles exist
    resp = requests.get(f"{BASE_URL}/admin/profiles", cookies=admin_cookies)
    if resp.status_code == 200:
        profiles = resp.json().get("profiles", [])
        log_test("5.5: At least 5 profiles exist after import",
                 len(profiles) >= 5,
                 f"Got {len(profiles)} profiles")

def test_import_edge_cases(admin_cookies):
    """Test 6: Import edge cases"""
    print("\n=== Test 6: Import Edge Cases ===")
    
    if not admin_cookies:
        print("⚠️  Skipping import edge cases - no admin cookies")
        return
    
    # 6.1: Empty text
    resp = requests.post(f"{BASE_URL}/admin/profiles/import",
                        cookies=admin_cookies,
                        json={"text": ""})
    log_test("6.1: Import with empty text returns 400 or 422",
             resp.status_code in [400, 422],
             f"Got {resp.status_code}: {resp.text}")
    
    # 6.2: Just whitespace
    resp = requests.post(f"{BASE_URL}/admin/profiles/import",
                        cookies=admin_cookies,
                        json={"text": "   \n\n   "})
    log_test("6.2: Import with just whitespace returns 400",
             resp.status_code == 400,
             f"Got {resp.status_code}: {resp.text}")
    
    # 6.3: Lines with no email/phone
    resp = requests.post(f"{BASE_URL}/admin/profiles/import",
                        cookies=admin_cookies,
                        json={"text": "just a name here\nanother name\nyet another"})
    log_test("6.3: Import with no email/phone lines returns 400",
             resp.status_code == 400,
             f"Got {resp.status_code}: {resp.text}")
    
    if resp.status_code == 400:
        log_test("6.4: Error message contains 'Aucune ligne exploitable détectée'",
                 "Aucune ligne exploitable détectée" in resp.text,
                 f"Got: {resp.text}")

def test_subscription_flow(alice_cookies):
    """Test 7: Subscription flow for profile user"""
    print("\n=== Test 7: Subscription Flow for Profile User ===")
    
    if not alice_cookies:
        print("⚠️  Skipping subscription flow tests - no alice cookies")
        return
    
    # 7.1: GET /api/subscription/canal
    resp = requests.get(f"{BASE_URL}/subscription/canal", cookies=alice_cookies)
    log_test("7.1: GET /api/subscription/canal returns 200",
             resp.status_code == 200,
             f"Got {resp.status_code}: {resp.text}")
    
    if resp.status_code == 200:
        data = resp.json()
        log_test("7.2: Subscription status='active'",
                 data.get("status") == "active",
                 f"Got status: {data.get('status')}")
    
    # 7.3: POST /api/subscription/canal/cancel
    resp = requests.post(f"{BASE_URL}/subscription/canal/cancel",
                        cookies=alice_cookies,
                        json={"reason": "Trop cher"})
    log_test("7.3: POST /api/subscription/canal/cancel returns 200",
             resp.status_code == 200,
             f"Got {resp.status_code}: {resp.text}")
    
    # 7.4: GET /api/subscription/canal after cancel
    resp = requests.get(f"{BASE_URL}/subscription/canal", cookies=alice_cookies)
    log_test("7.4: GET /api/subscription/canal after cancel returns 200",
             resp.status_code == 200,
             f"Got {resp.status_code}: {resp.text}")
    
    if resp.status_code == 200:
        data = resp.json()
        log_test("7.5: Subscription status='cancellation_requested'",
                 data.get("status") == "cancellation_requested",
                 f"Got status: {data.get('status')}")
        
        log_test("7.6: Cancellation has effective_date",
                 data.get("cancellation", {}).get("effective_date") is not None,
                 f"Got cancellation: {data.get('cancellation')}")
    
    # 7.7: POST /api/subscription/canal/cancel/undo
    resp = requests.post(f"{BASE_URL}/subscription/canal/cancel/undo",
                        cookies=alice_cookies)
    log_test("7.7: POST /api/subscription/canal/cancel/undo returns 200",
             resp.status_code == 200,
             f"Got {resp.status_code}: {resp.text}")
    
    # 7.8: GET /api/subscription/canal after undo
    resp = requests.get(f"{BASE_URL}/subscription/canal", cookies=alice_cookies)
    log_test("7.8: GET /api/subscription/canal after undo returns 200",
             resp.status_code == 200,
             f"Got {resp.status_code}: {resp.text}")
    
    if resp.status_code == 200:
        data = resp.json()
        log_test("7.9: Subscription status='active' after undo",
                 data.get("status") == "active",
                 f"Got status: {data.get('status')}")

def test_removed_endpoints():
    """Test 8: Removed endpoints"""
    print("\n=== Test 8: Removed Endpoints ===")
    
    # 8.1: POST /api/auth/register
    resp = requests.post(f"{BASE_URL}/auth/register", json={
        "email": "test@test.fr",
        "password": "password123",
        "name": "Test User"
    })
    log_test("8.1: POST /api/auth/register returns 404 or 405",
             resp.status_code in [404, 405],
             f"Got {resp.status_code}: {resp.text}")
    
    # 8.2: POST /api/auth/forgot-password
    resp = requests.post(f"{BASE_URL}/auth/forgot-password", json={
        "email": "test@test.fr"
    })
    log_test("8.2: POST /api/auth/forgot-password returns 404 or 405",
             resp.status_code in [404, 405],
             f"Got {resp.status_code}: {resp.text}")
    
    # 8.3: POST /api/auth/reset-password
    resp = requests.post(f"{BASE_URL}/auth/reset-password", json={
        "token": "sometoken",
        "password": "newpassword"
    })
    log_test("8.3: POST /api/auth/reset-password returns 404 or 405",
             resp.status_code in [404, 405],
             f"Got {resp.status_code}: {resp.text}")

def main():
    print(f"Backend URL: {BASE_URL}")
    print(f"Admin credentials: {ADMIN_EMAIL} / {ADMIN_PASSWORD}")
    print("=" * 80)
    
    # Test 1: Admin auth
    admin_cookies = test_admin_auth()
    
    if not admin_cookies:
        print("\n❌ CRITICAL: Admin authentication failed. Cannot continue.")
        return 1
    
    # Wipe customer_profiles before testing
    wipe_customer_profiles(admin_cookies)
    
    # Test 2: Admin CRUD
    test_admin_crud(admin_cookies)
    
    # Test 3: Profile login
    alice_id, alice_cookies = test_profile_login(admin_cookies)
    
    # Test 4: Non-admin access
    test_non_admin_access(alice_cookies)
    
    # Test 5: Bulk import
    test_bulk_import(admin_cookies)
    
    # Test 6: Import edge cases
    test_import_edge_cases(admin_cookies)
    
    # Test 7: Subscription flow
    test_subscription_flow(alice_cookies)
    
    # Test 8: Removed endpoints
    test_removed_endpoints()
    
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
