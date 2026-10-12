#====================================================================================================
# START - Testing Protocol - DO NOT EDIT OR REMOVE THIS SECTION
#====================================================================================================

# THIS SECTION CONTAINS CRITICAL TESTING INSTRUCTIONS FOR BOTH AGENTS
# BOTH MAIN_AGENT AND TESTING_AGENT MUST PRESERVE THIS ENTIRE BLOCK

# Communication Protocol:
# If the `testing_agent` is available, main agent should delegate all testing tasks to it.
#
# You have access to a file called `test_result.md`. This file contains the complete testing state
# and history, and is the primary means of communication between main and the testing agent.
#
# Main and testing agents must follow this exact format to maintain testing data. 
# The testing data must be entered in yaml format Below is the data structure:
# 
## user_problem_statement: {problem_statement}
## backend:
##   - task: "Task name"
##     implemented: true
##     working: true  # or false or "NA"
##     file: "file_path.py"
##     stuck_count: 0
##     priority: "high"  # or "medium" or "low"
##     needs_retesting: false
##     status_history:
##         -working: true  # or false or "NA"
##         -agent: "main"  # or "testing" or "user"
##         -comment: "Detailed comment about status"
##
## frontend:
##   - task: "Task name"
##     implemented: true
##     working: true  # or false or "NA"
##     file: "file_path.js"
##     stuck_count: 0
##     priority: "high"  # or "medium" or "low"
##     needs_retesting: false
##     status_history:
##         -working: true  # or false or "NA"
##         -agent: "main"  # or "testing" or "user"
##         -comment: "Detailed comment about status"
##
## metadata:
##   created_by: "main_agent"
##   version: "1.0"
##   test_sequence: 0
##   run_ui: false
##
## test_plan:
##   current_focus:
##     - "Task name 1"
##     - "Task name 2"
##   stuck_tasks:
##     - "Task name with persistent issues"
##   test_all: false
##   test_priority: "high_first"  # or "sequential" or "stuck_first"
##
## agent_communication:
##     -agent: "main"  # or "testing" or "user"
##     -message: "Communication message between agents"

# Protocol Guidelines for Main agent
#
# 1. Update Test Result File Before Testing:
#    - Main agent must always update the `test_result.md` file before calling the testing agent
#    - Add implementation details to the status_history
#    - Set `needs_retesting` to true for tasks that need testing
#    - Update the `test_plan` section to guide testing priorities
#    - Add a message to `agent_communication` explaining what you've done
#
# 2. Incorporate User Feedback:
#    - When a user provides feedback that something is or isn't working, add this information to the relevant task's status_history
#    - Update the working status based on user feedback
#    - If a user reports an issue with a task that was marked as working, increment the stuck_count
#    - Whenever user reports issue in the app, if we have testing agent and task_result.md file so find the appropriate task for that and append in status_history of that task to contain the user concern and problem as well 
#
# 3. Track Stuck Tasks:
#    - Monitor which tasks have high stuck_count values or where you are fixing same issue again and again, analyze that when you read task_result.md
#    - For persistent issues, use websearch tool to find solutions
#    - Pay special attention to tasks in the stuck_tasks list
#    - When you fix an issue with a stuck task, don't reset the stuck_count until the testing agent confirms it's working
#
# 4. Provide Context to Testing Agent:
#    - When calling the testing agent, provide clear instructions about:
#      - Which tasks need testing (reference the test_plan)
#      - Any authentication details or configuration needed
#      - Specific test scenarios to focus on
#      - Any known issues or edge cases to verify
#
# 5. Call the testing agent with specific instructions referring to test_result.md
#
# IMPORTANT: Main agent must ALWAYS update test_result.md BEFORE calling the testing agent, as it relies on this file to understand what to test next.

#====================================================================================================
# END - Testing Protocol - DO NOT EDIT OR REMOVE THIS SECTION
#====================================================================================================



#====================================================================================================
# Testing Data - Main Agent and testing sub agent both should log testing data below this section
#====================================================================================================

user_problem_statement: "Admin panel to manage per-user mapping: identifier (email/phone) → holder name + last 4 digits of IBAN. User espace client must display name + IBAN from this mapping. Make 'Résilier mon abonnement' button more visible. Remove 'Abonné depuis le 12 mars 2023' from the cancellation page."

backend:
  - task: "Admin CRUD endpoints for customer_profiles mapping"
    implemented: true
    working: true
    file: "backend/server.py"
    stuck_count: 0
    priority: "high"
    needs_retesting: false
    status_history:
        - working: "NA"
          agent: "main"
          comment: "Added GET/POST/PUT/DELETE /api/admin/profiles guarded by get_admin_user. Collection customer_profiles with unique identifier index. Validates iban_last4 to exactly 4 digits (or empty)."
        - working: true
          agent: "testing"
          comment: "✅ ALL TESTS PASSED (21/21). Admin auth guard: ✅ Admin login returns role=admin, ✅ GET /api/admin/profiles with admin cookie returns 200, ✅ Non-admin users get 403 with correct message 'Accès réservé aux administrateurs.' CRUD operations: ✅ POST creates profile with id, ✅ POST duplicate identifier returns 400 with correct message, ✅ POST with invalid iban_last4 (2 digits) returns 400, ✅ POST with empty iban_last4 returns 200, ✅ PUT updates name and iban_last4 correctly, ✅ PUT with invalid ObjectId returns 400, ✅ PUT to non-existing id returns 404, ✅ GET lists all profiles including created ones, ✅ DELETE returns 200, ✅ DELETE again returns 404. Identifier normalization: ✅ Email identifiers stored lowercased and trimmed, ✅ Phone identifiers normalized to digits + '+' only."

  - task: "public_user overlay with admin-managed name & iban_last4"
    implemented: true
    working: true
    file: "backend/server.py"
    stuck_count: 0
    priority: "high"
    needs_retesting: false
    status_history:
        - working: "NA"
          agent: "main"
          comment: "public_user is now async and looks up customer_profiles by lowercased email. Returns display_name=profile.name (fallback to prenom/nom/name) and iban_masked derived from iban_last4 when profile present. All callers (/auth/register, /auth/login, /auth/me, /profile) awaited."
        - working: true
          agent: "testing"
          comment: "✅ ALL TESTS PASSED (11/11). Overlay behavior: ✅ Created profile for test user with name='MARTIN Alice' and iban_last4='1234', ✅ GET /api/auth/me returns user.name='MARTIN Alice' (overlay applied), ✅ user.iban_masked='•••• •••• •••• 1234' (correctly formatted), ✅ user.has_iban=true, ✅ user.managed_by_admin=true when profile exists. After profile deletion: ✅ user.managed_by_admin=false, ✅ user.has_iban=false (fallback to user record). Identifier normalization in overlay: ✅ Profile with ' ADMIN@Bouygues.LOCAL ' (spaces + mixed case) correctly matches admin@bouygues.local user, ✅ Admin user gets overlay with name='Admin Test' and iban_masked='•••• •••• •••• 5678', ✅ Phone identifier '+33 6 12 34 56 78' normalized to '+33612345678'."

frontend:
  - task: "Admin page /admin/profils (CRUD UI)"
    implemented: true
    working: "NA"
    file: "frontend/src/pages/AdminProfiles.jsx"
    stuck_count: 0
    priority: "high"
    needs_retesting: false
    status_history:
        - working: "NA"
          agent: "main"
          comment: "New route /admin/profils accessible only to role=admin. List + search + create + edit + delete modal."

  - task: "Dashboard shows admin-managed name & IBAN; prominent Résilier button; admin link in header"
    implemented: true
    working: "NA"
    file: "frontend/src/pages/Dashboard.jsx"
    stuck_count: 0
    priority: "high"
    needs_retesting: false
    status_history:
        - working: "NA"
          agent: "main"
          comment: "fullName uses user.name (overlay) first; Résilier is now a solid orange filled button; admin link shown in header when role=admin; edit button hidden when managed_by_admin."

  - task: "Cancellation page: remove 'Abonné depuis le 12 mars 2023'"
    implemented: true
    working: "NA"
    file: "frontend/src/pages/CanalCancellation.jsx"
    stuck_count: 0
    priority: "medium"
    needs_retesting: false
    status_history:
        - working: "NA"
          agent: "main"
          comment: "Only price displayed; subscription-since line removed."

metadata:
  created_by: "main_agent"
  version: "1.2"
  test_sequence: 2
  run_ui: false

test_plan:
  current_focus: []
  stuck_tasks: []
  test_all: false
  test_priority: "high_first"

agent_communication:
    - agent: "main"
      message: "Please test /api/admin/profiles CRUD with admin credentials from /app/memory/test_credentials.md (admin@bouygues.local / Admin123!). Non-admin users must get 403. Also verify the overlay: create a profile with identifier matching a logged-in regular user's email; /api/auth/me for that user must return name=profile.name and iban_masked='•••• •••• •••• XXXX'. If no profile matches, /auth/me must still work with fallback (name may be empty, has_iban=false). Verify iban_last4 validation (must be exactly 4 digits or empty)."
    - agent: "testing"
      message: "✅ Backend testing complete. All 38 tests passed (100% success rate). Both high-priority backend tasks are fully working: (1) Admin CRUD endpoints for customer_profiles mapping - all operations (GET/POST/PUT/DELETE) work correctly with proper auth guards, validation, and error handling. (2) public_user overlay - correctly applies admin-managed name and iban_last4 to /api/auth/me response, with proper fallback when no profile exists. Identifier normalization works for both email (lowercased) and phone (digits + '+' only). No critical or major issues found. Backend implementation is production-ready."