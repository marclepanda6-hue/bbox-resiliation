#!/usr/bin/env python3
"""
Backend API tests for admin customer_profiles mapping and public_user overlay.
Tests admin CRUD endpoints and /api/auth/me overlay behavior.
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
ADMIN_EMAIL = "admin@bouygues.local"
ADMIN_PASSWORD = "Admin123!"

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

def test_admin_auth_guard():
    """Test 1: Admin auth guard"""
    print("\n=== Test 1: Admin Auth Guard ===")
    
    # 1.1: Login as admin
    resp = requests.post(f"{BASE_URL}/auth/login", json={
        "email": ADMIN_EMAIL,
        "password": ADMIN_PASSWORD
    })
    log_test("1.1: Admin login returns 200", resp.status_code == 200, 
             f"Got {resp.status_code}: {resp.text}")
    
    if resp.status_code != 200:
        return None, None
    
    admin_cookies = resp.cookies
    data = resp.json()
    log_test("1.2: Admin user has role=admin", 
             data.get("user", {}).get("role") == "admin",
             f"Got role={data.get('user', {}).get('role')}")
    
    # 1.3: GET /api/admin/profiles with admin cookie
    resp = requests.get(f"{BASE_URL}/admin/profiles", cookies=admin_cookies)
    log_test("1.3: GET /api/admin/profiles with admin cookie returns 200",
             resp.status_code == 200,
             f"Got {resp.status_code}: {resp.text}")
    
    # 1.4: Register a non-admin test user
    test_email = f"testuser_{datetime.now().timestamp()}@test.local"
    test_password = "TestPass123!"
    resp = requests.post(f"{BASE_URL}/auth/register", json={
        "email": test_email,
        "password": test_password,
        "name": "Test User"
    })
    log_test("1.4: Register non-admin user returns 200",
             resp.status_code == 200,
             f"Got {resp.status_code}: {resp.text}")
    
    if resp.status_code != 200:
        return admin_cookies, None
    
    # 1.5: Login as non-admin user
    resp = requests.post(f"{BASE_URL}/auth/login", json={
        "email": test_email,
        "password": test_password
    })
    log_test("1.5: Non-admin user login returns 200",
             resp.status_code == 200,
             f"Got {resp.status_code}: {resp.text}")
    
    if resp.status_code != 200:
        return admin_cookies, test_email
    
    user_cookies = resp.cookies
    
    # 1.6: GET /api/admin/profiles as non-admin must return 403
    resp = requests.get(f"{BASE_URL}/admin/profiles", cookies=user_cookies)
    log_test("1.6: GET /api/admin/profiles as non-admin returns 403",
             resp.status_code == 403,
             f"Got {resp.status_code}: {resp.text}")
    
    if resp.status_code == 403:
        log_test("1.7: 403 response contains correct message",
                 "Accès réservé aux administrateurs" in resp.text,
                 f"Got message: {resp.text}")
    
    return admin_cookies, test_email

def test_admin_crud(admin_cookies, test_email):
    """Test 2: CRUD on /api/admin/profiles"""
    print("\n=== Test 2: Admin CRUD on /api/admin/profiles ===")
    
    if not admin_cookies:
        print("⚠️  Skipping CRUD tests - no admin cookies")
        return None
    
    # 2.1: POST /api/admin/profiles with valid data
    resp = requests.post(f"{BASE_URL}/admin/profiles", 
                        cookies=admin_cookies,
                        json={
                            "identifier": test_email,
                            "name": "DUPONT Jean",
                            "iban_last4": "4521"
                        })
    log_test("2.1: POST /api/admin/profiles with valid data returns 200",
             resp.status_code == 200,
             f"Got {resp.status_code}: {resp.text}")
    
    if resp.status_code != 200:
        return None
    
    profile_data = resp.json()
    profile_id = profile_data.get("profile", {}).get("id")
    log_test("2.2: Created profile has id",
             profile_id is not None,
             f"Got profile: {profile_data}")
    
    # 2.3: POST duplicate identifier returns 400
    resp = requests.post(f"{BASE_URL}/admin/profiles",
                        cookies=admin_cookies,
                        json={
                            "identifier": test_email,
                            "name": "MARTIN Alice",
                            "iban_last4": "1234"
                        })
    log_test("2.3: POST duplicate identifier returns 400",
             resp.status_code == 400,
             f"Got {resp.status_code}: {resp.text}")
    
    if resp.status_code == 400:
        log_test("2.4: Duplicate error message is correct",
                 "Un profil existe déjà avec cet identifiant" in resp.text,
                 f"Got: {resp.text}")
    
    # 2.5: POST with iban_last4="12" (only 2 digits) returns 400
    test_email2 = f"test2_{datetime.now().timestamp()}@test.local"
    resp = requests.post(f"{BASE_URL}/admin/profiles",
                        cookies=admin_cookies,
                        json={
                            "identifier": test_email2,
                            "name": "TEST User",
                            "iban_last4": "12"
                        })
    log_test("2.5: POST with iban_last4='12' (2 digits) returns 400",
             resp.status_code == 400,
             f"Got {resp.status_code}: {resp.text}")
    
    # 2.6: POST with iban_last4="" (empty) returns 200
    resp = requests.post(f"{BASE_URL}/admin/profiles",
                        cookies=admin_cookies,
                        json={
                            "identifier": test_email2,
                            "name": "TEST User",
                            "iban_last4": ""
                        })
    log_test("2.6: POST with iban_last4='' (empty) returns 200",
             resp.status_code == 200,
             f"Got {resp.status_code}: {resp.text}")
    
    profile2_id = None
    if resp.status_code == 200:
        profile2_id = resp.json().get("profile", {}).get("id")
    
    # 2.7: PUT /api/admin/profiles/{id} to change name and iban_last4
    if profile_id:
        resp = requests.put(f"{BASE_URL}/admin/profiles/{profile_id}",
                           cookies=admin_cookies,
                           json={
                               "identifier": test_email,
                               "name": "DUPONT Jean-Pierre",
                               "iban_last4": "9876"
                           })
        log_test("2.7: PUT /api/admin/profiles/{id} with valid data returns 200",
                 resp.status_code == 200,
                 f"Got {resp.status_code}: {resp.text}")
        
        if resp.status_code == 200:
            updated = resp.json().get("profile", {})
            log_test("2.8: Updated profile has new name",
                     updated.get("name") == "DUPONT Jean-Pierre",
                     f"Got name: {updated.get('name')}")
            log_test("2.9: Updated profile has new iban_last4",
                     updated.get("iban_last4") == "9876",
                     f"Got iban_last4: {updated.get('iban_last4')}")
    
    # 2.10: PUT with invalid ObjectId returns 400
    resp = requests.put(f"{BASE_URL}/admin/profiles/invalid_id",
                       cookies=admin_cookies,
                       json={
                           "identifier": test_email,
                           "name": "Test",
                           "iban_last4": "1234"
                       })
    log_test("2.10: PUT with invalid ObjectId returns 400",
             resp.status_code == 400,
             f"Got {resp.status_code}: {resp.text}")
    
    # 2.11: PUT to non-existing id returns 404
    # Use a unique identifier to avoid conflict with existing profiles
    unique_email = f"nonexisting_{datetime.now().timestamp()}@test.local"
    resp = requests.put(f"{BASE_URL}/admin/profiles/507f1f77bcf86cd799439011",
                       cookies=admin_cookies,
                       json={
                           "identifier": unique_email,
                           "name": "Test",
                           "iban_last4": "1234"
                       })
    log_test("2.11: PUT to non-existing id returns 404",
             resp.status_code == 404,
             f"Got {resp.status_code}: {resp.text}")
    
    # 2.12: GET /api/admin/profiles contains created profile
    resp = requests.get(f"{BASE_URL}/admin/profiles", cookies=admin_cookies)
    if resp.status_code == 200:
        profiles = resp.json().get("profiles", [])
        found = any(p.get("identifier") == test_email.lower() for p in profiles)
        log_test("2.12: GET /api/admin/profiles contains created profile",
                 found,
                 f"Looking for {test_email.lower()} in {len(profiles)} profiles")
    
    # 2.13: DELETE /api/admin/profiles/{id} returns 200
    if profile_id:
        resp = requests.delete(f"{BASE_URL}/admin/profiles/{profile_id}",
                              cookies=admin_cookies)
        log_test("2.13: DELETE /api/admin/profiles/{id} returns 200",
                 resp.status_code == 200,
                 f"Got {resp.status_code}: {resp.text}")
        
        # 2.14: DELETE again returns 404
        resp = requests.delete(f"{BASE_URL}/admin/profiles/{profile_id}",
                              cookies=admin_cookies)
        log_test("2.14: DELETE same profile again returns 404",
                 resp.status_code == 404,
                 f"Got {resp.status_code}: {resp.text}")
    
    # Clean up profile2
    if profile2_id:
        requests.delete(f"{BASE_URL}/admin/profiles/{profile2_id}", cookies=admin_cookies)
    
    return profile_id

def test_overlay_in_auth_me(admin_cookies, test_email):
    """Test 3: Overlay in /api/auth/me"""
    print("\n=== Test 3: Overlay in /api/auth/me ===")
    
    if not admin_cookies or not test_email:
        print("⚠️  Skipping overlay tests - missing admin cookies or test email")
        return
    
    # 3.1: Create profile for test user
    resp = requests.post(f"{BASE_URL}/admin/profiles",
                        cookies=admin_cookies,
                        json={
                            "identifier": test_email,
                            "name": "MARTIN Alice",
                            "iban_last4": "1234"
                        })
    log_test("3.1: Create profile for test user returns 200",
             resp.status_code == 200,
             f"Got {resp.status_code}: {resp.text}")
    
    if resp.status_code != 200:
        return
    
    profile_id = resp.json().get("profile", {}).get("id")
    
    # 3.2: Login as test user
    test_password = "TestPass123!"
    resp = requests.post(f"{BASE_URL}/auth/login", json={
        "email": test_email,
        "password": test_password
    })
    log_test("3.2: Login as test user returns 200",
             resp.status_code == 200,
             f"Got {resp.status_code}: {resp.text}")
    
    if resp.status_code != 200:
        # Clean up
        if profile_id:
            requests.delete(f"{BASE_URL}/admin/profiles/{profile_id}", cookies=admin_cookies)
        return
    
    user_cookies = resp.cookies
    
    # 3.3: GET /api/auth/me as test user
    resp = requests.get(f"{BASE_URL}/auth/me", cookies=user_cookies)
    log_test("3.3: GET /api/auth/me returns 200",
             resp.status_code == 200,
             f"Got {resp.status_code}: {resp.text}")
    
    if resp.status_code == 200:
        user_data = resp.json().get("user", {})
        
        # 3.4: user.name equals "MARTIN Alice"
        log_test("3.4: user.name equals 'MARTIN Alice'",
                 user_data.get("name") == "MARTIN Alice",
                 f"Got name: {user_data.get('name')}")
        
        # 3.5: user.iban_masked equals "•••• •••• •••• 1234"
        log_test("3.5: user.iban_masked equals '•••• •••• •••• 1234'",
                 user_data.get("iban_masked") == "•••• •••• •••• 1234",
                 f"Got iban_masked: {user_data.get('iban_masked')}")
        
        # 3.6: has_iban=true
        log_test("3.6: user.has_iban is true",
                 user_data.get("has_iban") == True,
                 f"Got has_iban: {user_data.get('has_iban')}")
        
        # 3.7: managed_by_admin=true
        log_test("3.7: user.managed_by_admin is true",
                 user_data.get("managed_by_admin") == True,
                 f"Got managed_by_admin: {user_data.get('managed_by_admin')}")
    
    # 3.8: Delete the profile
    if profile_id:
        resp = requests.delete(f"{BASE_URL}/admin/profiles/{profile_id}",
                              cookies=admin_cookies)
        log_test("3.8: Delete profile returns 200",
                 resp.status_code == 200,
                 f"Got {resp.status_code}: {resp.text}")
    
    # 3.9: GET /api/auth/me again
    resp = requests.get(f"{BASE_URL}/auth/me", cookies=user_cookies)
    log_test("3.9: GET /api/auth/me after profile deletion returns 200",
             resp.status_code == 200,
             f"Got {resp.status_code}: {resp.text}")
    
    if resp.status_code == 200:
        user_data = resp.json().get("user", {})
        
        # 3.10: managed_by_admin=false
        log_test("3.10: user.managed_by_admin is false after profile deletion",
                 user_data.get("managed_by_admin") == False,
                 f"Got managed_by_admin: {user_data.get('managed_by_admin')}")
        
        # 3.11: has_iban should be false if user never saved IBAN locally
        # (This depends on whether the user had a local IBAN before)
        log_test("3.11: user.has_iban is false after profile deletion",
                 user_data.get("has_iban") == False,
                 f"Got has_iban: {user_data.get('has_iban')}")

def test_identifier_normalization(admin_cookies):
    """Test 4: Identifier normalization"""
    print("\n=== Test 4: Identifier Normalization ===")
    
    if not admin_cookies:
        print("⚠️  Skipping normalization tests - no admin cookies")
        return
    
    # 4.1: Create profile with mixed case and spaces in email
    resp = requests.post(f"{BASE_URL}/admin/profiles",
                        cookies=admin_cookies,
                        json={
                            "identifier": " ADMIN@Bouygues.LOCAL ",
                            "name": "Admin Test",
                            "iban_last4": "5678"
                        })
    log_test("4.1: Create profile with ' ADMIN@Bouygues.LOCAL ' returns 200",
             resp.status_code == 200,
             f"Got {resp.status_code}: {resp.text}")
    
    profile1_id = None
    if resp.status_code == 200:
        profile1_id = resp.json().get("profile", {}).get("id")
        stored_identifier = resp.json().get("profile", {}).get("identifier")
        
        # 4.2: Identifier is stored lowercased and trimmed
        log_test("4.2: Identifier stored as 'admin@bouygues.local' (lowercased & trimmed)",
                 stored_identifier == "admin@bouygues.local",
                 f"Got identifier: {stored_identifier}")
    
    # 4.3: Login as admin and check overlay
    resp = requests.post(f"{BASE_URL}/auth/login", json={
        "email": ADMIN_EMAIL,
        "password": ADMIN_PASSWORD
    })
    
    if resp.status_code == 200:
        admin_user_cookies = resp.cookies
        resp = requests.get(f"{BASE_URL}/auth/me", cookies=admin_user_cookies)
        
        if resp.status_code == 200:
            user_data = resp.json().get("user", {})
            
            # 4.4: Admin user gets overlay (name and iban_masked)
            log_test("4.4: Admin user.name equals 'Admin Test' (overlay applied)",
                     user_data.get("name") == "Admin Test",
                     f"Got name: {user_data.get('name')}")
            
            log_test("4.5: Admin user.iban_masked equals '•••• •••• •••• 5678'",
                     user_data.get("iban_masked") == "•••• •••• •••• 5678",
                     f"Got iban_masked: {user_data.get('iban_masked')}")
    
    # Clean up
    if profile1_id:
        requests.delete(f"{BASE_URL}/admin/profiles/{profile1_id}", cookies=admin_cookies)
    
    # 4.6: Create profile with phone number
    resp = requests.post(f"{BASE_URL}/admin/profiles",
                        cookies=admin_cookies,
                        json={
                            "identifier": "+33 6 12 34 56 78",
                            "name": "Phone User",
                            "iban_last4": "9999"
                        })
    log_test("4.6: Create profile with phone '+33 6 12 34 56 78' returns 200",
             resp.status_code == 200,
             f"Got {resp.status_code}: {resp.text}")
    
    profile2_id = None
    if resp.status_code == 200:
        profile2_id = resp.json().get("profile", {}).get("id")
        stored_identifier = resp.json().get("profile", {}).get("identifier")
        
        # 4.7: Phone identifier normalized to digits + '+'
        log_test("4.7: Phone identifier stored as '+33612345678' (normalized)",
                 stored_identifier == "+33612345678",
                 f"Got identifier: {stored_identifier}")
    
    # Clean up
    if profile2_id:
        requests.delete(f"{BASE_URL}/admin/profiles/{profile2_id}", cookies=admin_cookies)

def main():
    print(f"Backend URL: {BASE_URL}")
    print(f"Admin credentials: {ADMIN_EMAIL} / {ADMIN_PASSWORD}")
    print("=" * 60)
    
    # Run all tests
    admin_cookies, test_email = test_admin_auth_guard()
    test_admin_crud(admin_cookies, test_email)
    test_overlay_in_auth_me(admin_cookies, test_email)
    test_identifier_normalization(admin_cookies)
    
    # Summary
    print("\n" + "=" * 60)
    print(f"TESTS PASSED: {tests_passed}")
    print(f"TESTS FAILED: {tests_failed}")
    
    if failures:
        print("\n❌ FAILURES:")
        for failure in failures:
            print(f"  - {failure}")
    
    print("=" * 60)
    
    return 0 if tests_failed == 0 else 1

if __name__ == "__main__":
    sys.exit(main())
