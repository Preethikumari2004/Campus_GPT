# MCA CampusAI — Requirements and Planning Notes

_Last updated: 2026-10-03_
_Status: evolving plan; no feature here is considered approved for implementation unless marked confirmed._

## Project purpose

Build a realistic MCA academic assistant that is useful in students’ and faculty’s day-to-day work and can be presented to the Head of Department (HOD). Prioritize correct, useful academic information and dependable core workflows over a large number of unfinished screens.

## Roles and separate workspaces

The product has three account roles, each with a distinct interface:

- **Student:** their own courses, attendance, academic notices/schedule, and MCA CampusAI question answering.
- **Faculty:** teaching workspace, subject/course selection, their student roster, and teaching workflows such as attendance.
- **Admin:** account and system administration, plus management of approved knowledge documents.

Role names and login already exist in the project. Role-specific screens are underway; actual academic records and workflows still need to be completed and checked.

## Core priorities for the MVP

1. **Course and specialization catalog**
   - Add the MCA specializations and subjects that are actually used by the program.
   - When faculty selects a subject, use a searchable selector with choices from this catalog rather than a free-text field.
   - The exact specialization names, subject names, semesters, and faculty/course relationships are not collected yet.

2. **College knowledge base and AI answers**
   - This is a main project priority.
   - Collect suitable academic and campus information from authoritative, college-approved sources.
   - Keep the source name for each item and show citations/source excerpts with AI answers.
   - Gather the files first; decide supported formats and upload workflow after reviewing what is available. Current backend only reads `.txt` and `.md`; PDF support is not yet confirmed.
   - Confirm permission to use each source; do not add private student records or credentials to the knowledge base.

3. **Real login and attendance workflows**
   - Login should identify the signed-in role and show the right workspace.
   - Faculty should be able to record attendance for a relevant course and student group; students should see only their own attendance.
   - Current project code has an initial attendance implementation, but it has not yet been verified and does not yet model course enrollment. Do not treat it as complete.
   - A prior message included the ambiguous phrase “attendance login, that will clear everything.” Clarify what “clear everything” means before changing, deleting, or resetting any accounts or attendance records.

4. **Role-specific everyday academic tools**
   - Student, faculty, and admin screens should have different relevant actions.
   - Prioritize features that can be demonstrated with real data and role checks. Assignments, marks, calendar, notices, and detailed course management remain to be prioritized once the required data and HOD/project requirements are known.

## Future feature

- **MCA puzzle / quiz game:** simple subject-related puzzles or knowledge questions. This is a later feature, after login, courses, attendance, and the knowledge-base assistant are reliable.

## Information to collect

| Item | Why we need it | Status |
|---|---|---|
| MCA specializations offered | Populate the faculty searchable selector and role dashboards | Not collected |
| Subject list for each specialization and semester | Connect faculty and student course views to the real curriculum | Not collected |
| Approved syllabus / course outlines | Ground AI answers and show citations | Not collected |
| Attendance policy and workflow | Define how attendance is recorded and what students see | Not collected |
| Academic calendar, exam dates, and assignment rules | Add reliable schedules and student reminders | Not collected |
| HOD/project rubric or required demo checklist | Keep MVP aligned with evaluation requirements | Not collected |
| Source/owner and permission for each document | Ensure sources are suitable to include | Not collected |

Use sample/demo accounts and synthetic records for the presentation unless the college has approved the use of real student information.

## Working approach

- Keep adding new ideas to this note as they come up; label each as **MVP**, **later**, or **needs clarification**.
- Do not implement new features while the user is still defining the structure.
- Before coding each feature, agree on its screen, role permissions, data needed, and what counts as complete.
- Build and review one end-to-end feature at a time, then use it in the HOD demo.