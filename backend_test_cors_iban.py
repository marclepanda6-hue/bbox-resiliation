#!/usr/bin/env python3
"""
Backend API tests for CORS fix, new IBAN mask format, and full IBAN import.
Tests the 3 new features requested in the review.
"""

import os
import sys
import requests
import json

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

def test_cors_preflight():
    """Test 1: CORS preflight with various origins"""
    print("\n=== Test 1: CORS Preflight (PRIMARY FOCUS) ===")
    
    # Test origins that MUST be allowed
    allowed_origins = [
        "https://reset-abonnement.deployed.emergentagent.com",
        "https://gestion-clients-app.preview.emergentagent.com",
        "https://bar.emergent.host",
        "http://localhost:3000",
        "http://localhost:5173",
    ]
    
    for origin in allowed_origins:
        resp = requests.options(
            f"{BASE_URL}/auth/login",
            headers={
                "Origin": origin,
                "Access-Control-Request-Method": "POST",
                "Access-Control-Request-Headers": "content-type"
            }
        )
        
        # Check status code
        status_ok = resp.status_code in [200, 204]
        log_test(f"1.{allowed_origins.index(origin)+1}a: OPTIONS preflight for {origin} returns 200/204",
                 status_ok,
                 f"Got {resp.status_code}")
        
        if status_ok:
            headers = {k.lower(): v for k, v in resp.headers.items()}
            
            # Check Access-Control-Allow-Origin
            allow_origin = headers.get("access-control-allow-origin", "")
            log_test(f"1.{allowed_origins.index(origin)+1}b: Access-Control-Allow-Origin echoes {origin}",
                     allow_origin == origin,
                     f"Got: {allow_origin}")
            
            # Check Access-Control-Allow-Credentials
            allow_creds = headers.get("access-control-allow-credentials", "")
            log_test(f"1.{allowed_origins.index(origin)+1}c: Access-Control-Allow-Credentials is 'true'",
                     allow_creds.lower() == "true",
                     f"Got: {allow_creds}")
            
            # Check Access-Control-Allow-Methods includes POST
            allow_methods = headers.get("access-control-allow-methods", "").lower()
            log_test(f"1.{allowed_origins.index(origin)+1}d: Access-Control-Allow-Methods includes POST",
                     "post" in allow_methods,
                     f"Got: {allow_methods}")
            
            # Check Access-Control-Allow-Headers includes content-type
            allow_headers = headers.get("access-control-allow-headers", "").lower()
            log_test(f"1.{allowed_origins.index(origin)+1}e: Access-Control-Allow-Headers includes content-type",
                     "content-type" in allow_headers,
                     f"Got: {allow_headers}")
    
    # Test origin that must NOT be allowed
    evil_origin = "https://evil.example.com"
    resp = requests.options(
        f"{BASE_URL}/auth/login",
        headers={
            "Origin": evil_origin,
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "content-type"
        }
    )
    
    headers = {k.lower(): v for k, v in resp.headers.items()}
    allow_origin = headers.get("access-control-allow-origin", "")
    
    # The response should either omit the header or not echo the evil origin
    blocked = (allow_origin == "" or allow_origin != evil_origin)
    log_test(f"1.{len(allowed_origins)+1}: Evil origin {evil_origin} is NOT allowed",
             blocked,
             f"Got Access-Control-Allow-Origin: {allow_origin}")

def test_new_iban_mask_format(admin_cookies):
    """Test 2: New IBAN mask format"""
    print("\n=== Test 2: New IBAN Mask Format ===")
    
    if not admin_cookies:
        print("⚠️  Skipping IBAN mask tests - no admin cookies")
        return
    
    # Create profile with iban_last4="4521"
    resp = requests.post(f"{BASE_URL}/admin/profiles",
                        cookies=admin_cookies,
                        json={
                            "email": "test-mask@x.fr",
                            "name": "Test MASK",
                            "iban_last4": "4521"
                        })
    log_test("2.1: Create profile with iban_last4='4521' returns 200",
             resp.status_code == 200,
             f"Got {resp.status_code}: {resp.text}")
    
    if resp.status_code != 200:
        return
    
    # Login as that profile
    resp = requests.post(f"{BASE_URL}/auth/login", json={
        "email": "test-mask@x.fr",
        "password": "anypassword"
    })
    log_test("2.2: Login as test-mask@x.fr returns 200",
             resp.status_code == 200,
             f"Got {resp.status_code}: {resp.text}")
    
    if resp.status_code != 200:
        return
    
    mask_cookies = resp.cookies
    
    # GET /api/auth/me
    resp = requests.get(f"{BASE_URL}/auth/me", cookies=mask_cookies)
    log_test("2.3: GET /api/auth/me returns 200",
             resp.status_code == 200,
             f"Got {resp.status_code}: {resp.text}")
    
    if resp.status_code == 200:
        user = resp.json().get("user", {})
        iban_masked = user.get("iban_masked", "")
        expected = "FR76 •••• •••• •••• •••• 4521"
        
        log_test("2.4: iban_masked equals 'FR76 •••• •••• •••• •••• 4521'",
                 iban_masked == expected,
                 f"Got: '{iban_masked}' | Expected: '{expected}'")
    
    # Test with empty iban_last4
    resp = requests.post(f"{BASE_URL}/admin/profiles",
                        cookies=admin_cookies,
                        json={
                            "email": "test-empty@x.fr",
                            "name": "Test EMPTY",
                            "iban_last4": ""
                        })
    
    if resp.status_code == 200:
        resp = requests.post(f"{BASE_URL}/auth/login", json={
            "email": "test-empty@x.fr",
            "password": "anypassword"
        })
        
        if resp.status_code == 200:
            resp = requests.get(f"{BASE_URL}/auth/me", cookies=resp.cookies)
            if resp.status_code == 200:
                user = resp.json().get("user", {})
                iban_masked = user.get("iban_masked", "")
                log_test("2.5: iban_masked for empty iban_last4 is empty string",
                         iban_masked == "",
                         f"Got: '{iban_masked}'")

def test_import_full_iban(admin_cookies):
    """Test 3: Import accepts full IBAN"""
    print("\n=== Test 3: Import Accepts Full IBAN ===")
    
    if not admin_cookies:
        print("⚠️  Skipping full IBAN import tests - no admin cookies")
        return
    
    # Import with full IBANs
    import_text = """ibanfull-1@x.fr,0612000111,Jean DUPONT,FR76 3000 4000 0000 0000 4521
ibanfull-2@x.fr;0612000222;Marie BERNARD;FR7612345678901234567891234
ibanfull-3@x.fr | 0612000333 | Bob BLANC | GB82 WEST 1234 5698 7654 32"""
    
    resp = requests.post(f"{BASE_URL}/admin/profiles/import",
                        cookies=admin_cookies,
                        json={"text": import_text})
    log_test("3.1: POST /api/admin/profiles/import with full IBANs returns 200",
             resp.status_code == 200,
             f"Got {resp.status_code}: {resp.text}")
    
    if resp.status_code == 200:
        result = resp.json()
        created = result.get("created", 0)
        log_test("3.2: Import created >= 3 profiles",
                 created >= 3,
                 f"Got created={created}")
    
    # Verify the profiles
    resp = requests.get(f"{BASE_URL}/admin/profiles", cookies=admin_cookies)
    if resp.status_code == 200:
        profiles = resp.json().get("profiles", [])
        
        # Check ibanfull-1@x.fr -> iban_last4="4521"
        profile1 = next((p for p in profiles if p.get("email") == "ibanfull-1@x.fr"), None)
        if profile1:
            log_test("3.3: ibanfull-1@x.fr has iban_last4='4521'",
                     profile1.get("iban_last4") == "4521",
                     f"Got iban_last4: {profile1.get('iban_last4')}")
        else:
            log_test("3.3: ibanfull-1@x.fr found", False, "Profile not found")
        
        # Check ibanfull-2@x.fr -> iban_last4="1234"
        profile2 = next((p for p in profiles if p.get("email") == "ibanfull-2@x.fr"), None)
        if profile2:
            log_test("3.4: ibanfull-2@x.fr has iban_last4='1234'",
                     profile2.get("iban_last4") == "1234",
                     f"Got iban_last4: {profile2.get('iban_last4')}")
        else:
            log_test("3.4: ibanfull-2@x.fr found", False, "Profile not found")
        
        # Check ibanfull-3@x.fr -> iban_last4="5432"
        profile3 = next((p for p in profiles if p.get("email") == "ibanfull-3@x.fr"), None)
        if profile3:
            log_test("3.5: ibanfull-3@x.fr has iban_last4='5432'",
                     profile3.get("iban_last4") == "5432",
                     f"Got iban_last4: {profile3.get('iban_last4')}")
        else:
            log_test("3.5: ibanfull-3@x.fr found", False, "Profile not found")
    
    # Login as one of these profiles and verify iban_masked
    resp = requests.post(f"{BASE_URL}/auth/login", json={
        "email": "ibanfull-1@x.fr",
        "password": "anypassword"
    })
    
    if resp.status_code == 200:
        resp = requests.get(f"{BASE_URL}/auth/me", cookies=resp.cookies)
        if resp.status_code == 200:
            user = resp.json().get("user", {})
            iban_masked = user.get("iban_masked", "")
            expected = "FR76 •••• •••• •••• •••• 4521"
            log_test("3.6: ibanfull-1@x.fr iban_masked uses new FR76 format",
                     iban_masked == expected,
                     f"Got: '{iban_masked}' | Expected: '{expected}'")

def test_regression(admin_cookies):
    """Test 4: Quick regression tests"""
    print("\n=== Test 4: Quick Regression Tests ===")
    
    # 4.1: Admin login with correct credentials
    resp = requests.post(f"{BASE_URL}/auth/login", json={
        "email": ADMIN_EMAIL,
        "password": ADMIN_PASSWORD
    })
    log_test("4.1: Admin login with correct credentials returns 200",
             resp.status_code == 200,
             f"Got {resp.status_code}: {resp.text}")
    
    # 4.2: Admin login with wrong password
    resp = requests.post(f"{BASE_URL}/auth/login", json={
        "email": ADMIN_EMAIL,
        "password": "wrongpassword"
    })
    log_test("4.2: Admin login with wrong password returns 401",
             resp.status_code == 401,
             f"Got {resp.status_code}: {resp.text}")
    
    # 4.3: Login with existing profile email
    if admin_cookies:
        # Create a test profile
        resp = requests.post(f"{BASE_URL}/admin/profiles",
                            cookies=admin_cookies,
                            json={
                                "email": "regression-test@x.fr",
                                "name": "Regression Test",
                                "iban_last4": "9999"
                            })
        
        if resp.status_code == 200:
            resp = requests.post(f"{BASE_URL}/auth/login", json={
                "email": "regression-test@x.fr",
                "password": "anypassword"
            })
            log_test("4.3: Login with existing profile email + any password returns 200",
                     resp.status_code == 200,
                     f"Got {resp.status_code}: {resp.text}")
    
    # 4.4: Login with unknown identifier
    resp = requests.post(f"{BASE_URL}/auth/login", json={
        "email": "unknown-user@x.fr",
        "password": "anypassword"
    })
    log_test("4.4: Login with unknown identifier returns 401",
             resp.status_code == 401,
             f"Got {resp.status_code}: {resp.text}")
    
    if resp.status_code == 401:
        log_test("4.5: Unknown identifier error is 'Identifiant non autorisé.'",
                 "Identifiant non autorisé" in resp.text,
                 f"Got: {resp.text}")
    
    # 4.6: GET /api/admin/profiles as non-admin
    resp = requests.get(f"{BASE_URL}/admin/profiles")
    log_test("4.6: GET /api/admin/profiles without auth returns 401",
             resp.status_code == 401,
             f"Got {resp.status_code}: {resp.text}")
    
    # 4.7: POST /api/auth/register
    resp = requests.post(f"{BASE_URL}/auth/register", json={
        "email": "test@test.fr",
        "password": "password123"
    })
    log_test("4.7: POST /api/auth/register returns 404 or 405",
             resp.status_code in [404, 405],
             f"Got {resp.status_code}: {resp.text}")

def main():
    print(f"Backend URL: {BASE_URL}")
    print(f"Admin credentials: {ADMIN_EMAIL} / {ADMIN_PASSWORD}")
    print("=" * 80)
    
    # Test 1: CORS preflight (PRIMARY FOCUS)
    test_cors_preflight()
    
    # Login as admin for remaining tests
    resp = requests.post(f"{BASE_URL}/auth/login", json={
        "email": ADMIN_EMAIL,
        "password": ADMIN_PASSWORD
    })
    
    admin_cookies = None
    if resp.status_code == 200:
        admin_cookies = resp.cookies
    else:
        print(f"\n❌ CRITICAL: Admin authentication failed ({resp.status_code}). Some tests will be skipped.")
    
    # Test 2: New IBAN mask format
    test_new_iban_mask_format(admin_cookies)
    
    # Test 3: Import accepts full IBAN
    test_import_full_iban(admin_cookies)
    
    # Test 4: Quick regression
    test_regression(admin_cookies)
    
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
