import { useEffect, useState } from 'react'
import allianceMcaLogo from './assets/alliance-mca-logo.png'
import SearchableSelect from './components/SearchableSelect'
import './App.css'

const API_BASE = import.meta.env.VITE_API_BASE || '/api'
const TOKEN_KEY = 'mca_campusai_token'
const REMEMBERED_USERNAME_KEY = 'mca_campusai_remembered_username'
const DEMO_ACCOUNTS = [
  { role: 'student', label: 'Student demo', username: 'student_demo', password: 'student1234' },
  { role: 'faculty', label: 'Faculty demo', username: 'faculty_demo', password: 'faculty1234' },
  { role: 'admin', label: 'Admin demo', username: 'admin_demo', password: 'admin1234' },
]

async function parseJsonResponse(response) {
  const text = await response.text()
  if (!text) return null

  try {
    return JSON.parse(text)
  } catch {
    return null
  }
}

function getApiErrorMessage(payload, fallback) {
  if (!payload) return fallback
  if (typeof payload === 'string' && payload.trim()) return payload
  if (typeof payload === 'object') {
    return payload.detail || payload.message || fallback
  }
  return fallback
}

function normalizeCampusGPTAnswer(value) {
  if (typeof value === 'string') {
    return value.replace(/\s*\[object Object\]\s*/g, ' ').replace(/\s{2,}/g, ' ').trim()
  }
  if (Array.isArray(value)) {
    return value.map(normalizeCampusGPTAnswer).filter(Boolean).join(' ')
  }
  if (value && typeof value === 'object') {
    for (const key of ['answer', 'text', 'content', 'message', 'detail']) {
      if (value[key] !== undefined) {
        const readable = normalizeCampusGPTAnswer(value[key])
        if (readable) return readable
      }
    }
    const subject = value.subject_name || value.name
    if (subject) {
      const details = [value.term, value.semester ? `Semester ${value.semester}` : '', value.code ? `Code ${value.code}` : '', value.faculty || value.instructor_name]
        .filter(Boolean)
      return details.length ? `${subject} (${details.join(', ')})` : String(subject)
    }
    return Object.values(value).map(normalizeCampusGPTAnswer).filter(Boolean).join(' ')
  }
  return value == null ? '' : String(value)
}

const roleNavigation = {
  student: [
    ['dashboard', '⌂', 'Dashboard'], ['chat', '✳', 'Ask AI'], ['courses', '▤', 'My Courses'], ['documents', '▧', 'My Documents'],
    ['assignments', '▧', 'Assignments'], ['calendar', '▦', 'Calendar'], ['exams', '▣', 'Exams'],
    ['attendance', '◷', 'Attendance'], ['history', '☷', 'Chat History'], ['profile', '◉', 'Profile'],
  ],
  faculty: [
    ['dashboard', '⌂', 'Teaching Home'], ['chat', '✳', 'Ask AI'], ['courses', '▤', 'Subject Catalog'], ['documents', '▧', 'Course Documents'],
    ['faculty-students', '♙', 'Student Roster'], ['assignments', '▧', 'Assignments'],
    ['attendance', '◷', 'Attendance'], ['calendar', '▦', 'Calendar'], ['profile', '◉', 'Profile'],
  ],
  admin: [
    ['dashboard', '⌂', 'Overview'], ['admin-faculty', '♙', 'Faculty Management'], ['admin-users', '♙', 'Student Management'], ['catalog', '▤', 'Course Catalog'],
    ['calendar', '▦', 'Campus Calendar'], ['documents', '▧', 'Knowledge Documents'], ['chat', '✳', 'Ask AI'],
  ],
}

const roles = [
  { value: 'student', label: 'Student' },
  { value: 'faculty', label: 'Faculty' },
  { value: 'admin', label: 'Admin' },
]

const roleSuggestions = {
  student: [
    'What subjects do I have this semester?',
    'Explain my Deep Learning syllabus.',
    'What are the attendance requirements?',
  ],
  faculty: [
    'Which subjects am I assigned to teach?',
    'Explain my Deep Learning syllabus.',
    'What are the attendance requirements?',
  ],
  admin: [
    'Who teaches Deep Learning Models and Applications?',
    'Which subjects are listed for Semester 3?',
    'What new subjects were added in the last 30 days?',
    'What exams and events are coming up?',
  ],
}

const emptyEventForm = { title: '', description: '', event_type: 'campus', start_at: '', end_at: '', location: '' }

function eventDateInput(value) {
  if (!value) return ''
  const parts = Object.fromEntries(new Intl.DateTimeFormat('en-CA', {
    timeZone: 'Asia/Kolkata', year: 'numeric', month: '2-digit', day: '2-digit',
    hour: '2-digit', minute: '2-digit', hourCycle: 'h23',
  }).formatToParts(new Date(value)).map((part) => [part.type, part.value]))
  return `${parts.year}-${parts.month}-${parts.day}T${parts.hour}:${parts.minute}`
}

function eventDateBadge(value) {
  const date = new Date(value)
  return {
    month: new Intl.DateTimeFormat('en-US', { month: 'short', timeZone: 'Asia/Kolkata' }).format(date).toUpperCase(),
    day: new Intl.DateTimeFormat('en-US', { day: '2-digit', timeZone: 'Asia/Kolkata' }).format(date),
  }
}

function eventDateTime(value) {
  return new Intl.DateTimeFormat('en-IN', {
    timeZone: 'Asia/Kolkata', dateStyle: 'medium', timeStyle: 'short',
  }).format(new Date(value))
}

function campusDateKey(value) {
  const parts = Object.fromEntries(new Intl.DateTimeFormat('en-CA', {
    timeZone: 'Asia/Kolkata', year: 'numeric', month: '2-digit', day: '2-digit',
  }).formatToParts(new Date(value)).map((part) => [part.type, part.value]))
  return `${parts.year}-${parts.month}-${parts.day}`
}

function App() {
  const [token, setToken] = useState(() => sessionStorage.getItem(TOKEN_KEY) || '')
  const [user, setUser] = useState(null)
  const suggestions = roleSuggestions[user?.role] || roleSuggestions.student
  const [checkingSession, setCheckingSession] = useState(Boolean(sessionStorage.getItem(TOKEN_KEY)))
  const [role, setRole] = useState('student')
  const [username, setUsername] = useState(() => localStorage.getItem(REMEMBERED_USERNAME_KEY) || '')
  const [rememberUsername, setRememberUsername] = useState(() => Boolean(localStorage.getItem(REMEMBERED_USERNAME_KEY)))
  const [password, setPassword] = useState('')
  const [showPassword, setShowPassword] = useState(false)
  const [loginLoading, setLoginLoading] = useState(false)
  const [loginError, setLoginError] = useState('')
  const [activePage, setActivePage] = useState('dashboard')
  const [toast, setToast] = useState(null)
  const [facultyProfile, setFacultyProfile] = useState({ full_name: '', email: '', username: '', role: 'faculty' })
  const [profileCurrentPassword, setProfileCurrentPassword] = useState('')
  const [profileNewPassword, setProfileNewPassword] = useState('')
  const [profileLoading, setProfileLoading] = useState(false)
  const [profileSaving, setProfileSaving] = useState(false)
  const [profileError, setProfileError] = useState('')
  const [profileNotice, setProfileNotice] = useState('')
  const [question, setQuestion] = useState('')
  const [conversation, setConversation] = useState([])
  const [activeChatId, setActiveChatId] = useState(null)
  const [chatHistory, setChatHistory] = useState([])
  const [chatHistoryLoading, setChatHistoryLoading] = useState(false)
  const [chatHistoryError, setChatHistoryError] = useState('')
  const [openingChatId, setOpeningChatId] = useState(null)
  const [deletingChatId, setDeletingChatId] = useState(null)
  const [clearingChatHistory, setClearingChatHistory] = useState(false)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')
  const [notice, setNotice] = useState('')
  const [knowledgeDocuments, setKnowledgeDocuments] = useState([])
  const [knowledgeDocsLoading, setKnowledgeDocsLoading] = useState(false)
  const [knowledgeFile, setKnowledgeFile] = useState(null)
  const [knowledgeUploadLoading, setKnowledgeUploadLoading] = useState(false)
  const [knowledgeDocsError, setKnowledgeDocsError] = useState('')
  const [knowledgeDocsNotice, setKnowledgeDocsNotice] = useState('')
  const [documentSubjects, setDocumentSubjects] = useState([])
  const [documentType, setDocumentType] = useState('campus')
  const [documentSubjectId, setDocumentSubjectId] = useState('')
  const [studentEnrollmentRows, setStudentEnrollmentRows] = useState([])
  const [enrollmentStudentId, setEnrollmentStudentId] = useState('')
  const [enrollmentSubjectIds, setEnrollmentSubjectIds] = useState([])
  const [roleRecords, setRoleRecords] = useState([])
  const [roleRecordsTotal, setRoleRecordsTotal] = useState(0)
  const [studentSearch, setStudentSearch] = useState('')
  const [studentOffset, setStudentOffset] = useState(0)
  const [selectedStudentIds, setSelectedStudentIds] = useState([])
  const [adminSummary, setAdminSummary] = useState({ students: 0, faculty: 0, courses: 0, subjects: 0, departments: 0 })
  const [recordsError, setRecordsError] = useState('')
  const [recordsLoading, setRecordsLoading] = useState(false)
  const [attendanceSummary, setAttendanceSummary] = useState({ present: 0, total: 0, percentage: 0, records: [] })
  const [attendanceLoading, setAttendanceLoading] = useState(false)
  const [attendanceError, setAttendanceError] = useState('')
  const [attendanceCourse, setAttendanceCourse] = useState('')
  const [attendanceDate, setAttendanceDate] = useState(() => {
    const today = new Date()
    return new Date(today.getTime() - today.getTimezoneOffset() * 60000).toISOString().slice(0, 10)
  })
  const [attendanceSaving, setAttendanceSaving] = useState(false)
  const [attendanceMessage, setAttendanceMessage] = useState('')
  const [attendanceMarks, setAttendanceMarks] = useState({})
  const [attendanceHistory, setAttendanceHistory] = useState([])
  const [attendanceHistoryLoading, setAttendanceHistoryLoading] = useState(false)
  const [attendanceHistoryError, setAttendanceHistoryError] = useState('')
  const [classAssignments, setClassAssignments] = useState([])
  const [classAssignmentsLoading, setClassAssignmentsLoading] = useState(false)
  const [classAssignmentsError, setClassAssignmentsError] = useState('')
  const [classAssignmentsNotice, setClassAssignmentsNotice] = useState('')
  const [classAssignmentSubjectId, setClassAssignmentSubjectId] = useState('')
  const [assignmentTitle, setAssignmentTitle] = useState('')
  const [assignmentInstructions, setAssignmentInstructions] = useState('')
  const [assignmentDueAt, setAssignmentDueAt] = useState('')
  const [assignmentSaving, setAssignmentSaving] = useState(false)
  const [studentResponses, setStudentResponses] = useState({})
  const [studentSubmissionFiles, setStudentSubmissionFiles] = useState({})
  const [submissionSavingId, setSubmissionSavingId] = useState(null)
  const [submissionsByAssignment, setSubmissionsByAssignment] = useState({})
  const [submissionReviews, setSubmissionReviews] = useState({})
  const [reviewSavingId, setReviewSavingId] = useState(null)
  const [campusEvents, setCampusEvents] = useState([])
  const [eventsLoading, setEventsLoading] = useState(false)
  const [eventsError, setEventsError] = useState('')
  const [eventsNotice, setEventsNotice] = useState('')
  const [eventForm, setEventForm] = useState(emptyEventForm)
  const [eventEditId, setEventEditId] = useState(null)
  const [eventSaving, setEventSaving] = useState(false)
  const [calendarMonth, setCalendarMonth] = useState(() => {
    const today = new Date()
    const year = today.getFullYear() >= 2026 && today.getFullYear() <= 2027 ? today.getFullYear() : 2026
    return new Date(year, year === today.getFullYear() ? today.getMonth() : 0, 1)
  })
  const [selectedCalendarDate, setSelectedCalendarDate] = useState(() => {
    const today = new Date()
    const date = today.getFullYear() >= 2026 && today.getFullYear() <= 2027 ? today : new Date(2026, 0, 1)
    return `${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, '0')}-${String(date.getDate()).padStart(2, '0')}`
  })
  const [specializations, setSpecializations] = useState([])
  const [specializationName, setSpecializationName] = useState('')
  const [specializationEditId, setSpecializationEditId] = useState(null)
  const [specializationFormOpen, setSpecializationFormOpen] = useState(false)
  const [courseName, setCourseName] = useState('')
  const [courseCode, setCourseCode] = useState('')
  const [courseSaving, setCourseSaving] = useState(false)
  const [courseEditId, setCourseEditId] = useState(null)
  const [courseFormOpen, setCourseFormOpen] = useState(false)
  const [subjects, setSubjects] = useState([])
  const [adminOptions, setAdminOptions] = useState({ faculty: [], courses: [], departments: [], term_sections: [] })
  const [facultyAssignments, setFacultyAssignments] = useState([])
  const [subjectCourseId, setSubjectCourseId] = useState('')
  const [assignmentFacultyId, setAssignmentFacultyId] = useState('')
  const [assignmentSubjectId, setAssignmentSubjectId] = useState('')
  const [customTerm, setCustomTerm] = useState(false)
  const [customSection, setCustomSection] = useState(false)
  const [catalogLoading, setCatalogLoading] = useState(false)
  const [catalogError, setCatalogError] = useState('')
  const [catalogNotice, setCatalogNotice] = useState('')
  const [subjectSpecialization, setSubjectSpecialization] = useState('')
  const [subjectCode, setSubjectCode] = useState('')
  const [subjectName, setSubjectName] = useState('')
  const [subjectSemester, setSubjectSemester] = useState('1')
  const [subjectTerm, setSubjectTerm] = useState('')
  const [subjectSection, setSubjectSection] = useState('')
  const [subjectEditId, setSubjectEditId] = useState(null)
  const [manualSubjectEntry, setManualSubjectEntry] = useState(false)
  const [allowSubjectIdentityEdit, setAllowSubjectIdentityEdit] = useState(false)
  const [subjectSearch, setSubjectSearch] = useState('')
  const [specializationFilter, setSpecializationFilter] = useState('')
  const [specializationListFilter, setSpecializationListFilter] = useState('')
  const [facultyFullName, setFacultyFullName] = useState('')
  const [facultyUsername, setFacultyUsername] = useState('')
  const [facultyEmail, setFacultyEmail] = useState('')
  const [facultyPassword, setFacultyPassword] = useState('')
  const [showFacultyInitialPassword, setShowFacultyInitialPassword] = useState(false)
  const [courseInstructors, setCourseInstructors] = useState([])
  const [facultySaving, setFacultySaving] = useState(false)
  const [facultyEditId, setFacultyEditId] = useState(null)
  const [facultyEditValues, setFacultyEditValues] = useState({ full_name: '', username: '', email: '' })
  const [studentFullName, setStudentFullName] = useState('')
  const [studentUsername, setStudentUsername] = useState('')
  const [studentEmail, setStudentEmail] = useState('')
  const [studentPassword, setStudentPassword] = useState('')
  const [showStudentInitialPassword, setShowStudentInitialPassword] = useState(false)
  const [studentEditId, setStudentEditId] = useState(null)
  const [studentEditValues, setStudentEditValues] = useState({ full_name: '', username: '', email: '' })

  function showToast(message, type = 'success') {
    setToast({ message, type, id: Date.now() })
  }

  useEffect(() => {
    if (!toast) return undefined
    const timer = window.setTimeout(() => setToast(null), 4500)
    return () => window.clearTimeout(timer)
  }, [toast])

  useEffect(() => {
    if (!token) return
    fetch(`${API_BASE}/auth/me`, { headers: { Authorization: `Bearer ${token}` } })
      .then(async (response) => {
        const result = await parseJsonResponse(response)
        if (!response.ok) throw new Error(getApiErrorMessage(result, 'Your login session has expired.'))
        setUser(result)
        setRole(result.role)
      })
      .catch(() => {
        sessionStorage.removeItem(TOKEN_KEY)
        setToken('')
      })
      .finally(() => setCheckingSession(false))
  }, [token])

  useEffect(() => {
    if (!token || !['student', 'faculty'].includes(user?.role) || activePage !== 'profile') return
    let cancelled = false
    setFacultyProfile({
      full_name: user.full_name || '',
      email: user.email || '',
      username: user.username || '',
      role: user.role,
    })
    setProfileLoading(true)
    setProfileError('')
    setProfileNotice('')
    fetch(`${API_BASE}/${user.role}/profile`, { headers: { Authorization: `Bearer ${token}` } })
      .then(async (response) => {
        const result = await parseJsonResponse(response)
        if (!response.ok) throw new Error(getApiErrorMessage(result, 'Could not load your profile.'))
        if (!cancelled) {
          setFacultyProfile({ full_name: result.full_name || '', email: result.email || '', username: result.username || '', role: result.role || 'faculty' })
          setUser((current) => ({ ...current, ...result }))
        }
      })
      .catch((requestError) => { if (!cancelled) setProfileError(requestError.message || 'Could not connect to the backend.') })
      .finally(() => { if (!cancelled) setProfileLoading(false) })
    return () => { cancelled = true }
  }, [token, user?.role, activePage])

  useEffect(() => {
    if (!token || user?.role !== 'admin' || activePage !== 'dashboard') return
    let cancelled = false
    fetch(`${API_BASE}/admin/dashboard/summary`, { headers: { Authorization: `Bearer ${token}` } })
      .then(async (response) => {
        const result = await parseJsonResponse(response)
        if (!response.ok) throw new Error(getApiErrorMessage(result, 'Could not load dashboard totals.'))
        if (!cancelled) setAdminSummary(result)
      })
      .catch((requestError) => { if (!cancelled) setNotice(requestError.message || 'Could not load dashboard totals.') })
    return () => { cancelled = true }
  }, [token, user, activePage])

  useEffect(() => {
    if (!token || !user || activePage !== 'documents') return
    let cancelled = false
    setKnowledgeDocsLoading(true)
    setKnowledgeDocsError('')
    const headers = { Authorization: `Bearer ${token}` }
    const subjectPath = user.role === 'faculty' ? '/faculty/subjects' : user.role === 'student' ? '/student/subjects' : '/admin/options'
    Promise.all([fetch(`${API_BASE}/documents`, { headers }), fetch(`${API_BASE}${subjectPath}`, { headers })])
      .then(async ([documentsResponse, subjectsResponse]) => {
        const [documentsResult, subjectsResult] = await Promise.all([parseJsonResponse(documentsResponse), parseJsonResponse(subjectsResponse)])
        if (!documentsResponse.ok) throw new Error(getApiErrorMessage(documentsResult, 'Could not load the knowledge documents.'))
        if (!subjectsResponse.ok) throw new Error(getApiErrorMessage(subjectsResult, 'Could not load your subject list.'))
        if (!cancelled) {
          setKnowledgeDocuments(documentsResult?.documents || [])
          setDocumentSubjects(user.role === 'admin' ? (subjectsResult?.subjects || []) : (subjectsResult?.subjects || []))
          if (user.role === 'admin') setAdminOptions((options) => ({ ...options, ...(subjectsResult || {}) }))
          setDocumentSubjectId((current) => current || String((subjectsResult?.subjects || [])[0]?.id || ''))
        }
      })
      .catch((requestError) => { if (!cancelled) setKnowledgeDocsError(requestError.message || 'Could not connect to the backend.') })
      .finally(() => { if (!cancelled) setKnowledgeDocsLoading(false) })
    return () => { cancelled = true }
  }, [token, user, activePage])

  useEffect(() => {
    if (!token || user?.role !== 'admin' || activePage !== 'catalog') return
    let cancelled = false
    fetch(`${API_BASE}/admin/enrollments`, { headers: { Authorization: `Bearer ${token}` } })
      .then(async (response) => {
        const result = await parseJsonResponse(response)
        if (!response.ok) throw new Error(getApiErrorMessage(result, 'Could not load student enrollments.'))
        if (!cancelled) setStudentEnrollmentRows(result?.enrollments || [])
      })
      .catch((requestError) => { if (!cancelled) setCatalogError(requestError.message || 'Could not load enrollments.') })
    return () => { cancelled = true }
  }, [token, user, activePage, subjects.length, adminOptions.students?.length])

  useEffect(() => {
    const facultyAttendance = activePage === 'attendance' && user?.role === 'faculty'
    if (!token || !user || (!['admin-users', 'admin-faculty', 'faculty-students'].includes(activePage) && !facultyAttendance)) return
    const endpoint = activePage === 'admin-users' ? '/admin/students' : activePage === 'admin-faculty' ? '/admin/faculty' : '/faculty/students'
    const collection = activePage === 'admin-users' ? 'students' : activePage === 'admin-faculty' ? 'faculty' : 'students'
    let cancelled = false
    setRecordsLoading(true)
    setRecordsError('')
    const query = activePage === 'admin-users'
      ? `?limit=25&offset=${studentOffset}&search=${encodeURIComponent(studentSearch)}`
      : activePage === 'attendance' && attendanceCourse
        ? `?subject_id=${encodeURIComponent(attendanceCourse)}`
        : ''
    fetch(`${API_BASE}${endpoint}${query}`, { headers: { Authorization: `Bearer ${token}` } })
      .then(async (response) => {
        const result = await parseJsonResponse(response)
        if (!response.ok) throw new Error(getApiErrorMessage(result, 'Could not load this list.'))
        if (!cancelled) {
          setRoleRecords(result[collection] || [])
          if (activePage === 'admin-users') setRoleRecordsTotal(result.total || 0)
          if (activePage === 'admin-faculty') setCourseInstructors(result.course_instructors || [])
        }
      })
      .catch((requestError) => {
        if (!cancelled) setRecordsError(requestError.message || 'Could not connect to the backend.')
      })
      .finally(() => { if (!cancelled) setRecordsLoading(false) })
    return () => { cancelled = true }
  }, [token, user, activePage, studentSearch, studentOffset, attendanceCourse])

  useEffect(() => {
    if (!token || user?.role !== 'faculty' || activePage !== 'attendance') return
    let cancelled = false
    setAttendanceHistoryLoading(true)
    setAttendanceHistoryError('')
    const subjectQuery = attendanceCourse ? `?subject_id=${encodeURIComponent(attendanceCourse)}` : ''
    fetch(`${API_BASE}/faculty/attendance${subjectQuery}`, { headers: { Authorization: `Bearer ${token}` } })
      .then(async (response) => {
        const result = await parseJsonResponse(response)
        if (!response.ok) throw new Error(getApiErrorMessage(result, 'Could not load attendance history.'))
        if (!cancelled) setAttendanceHistory(result?.sessions || [])
      })
      .catch((requestError) => { if (!cancelled) setAttendanceHistoryError(requestError.message || 'Could not load attendance history.') })
      .finally(() => { if (!cancelled) setAttendanceHistoryLoading(false) })
    return () => { cancelled = true }
  }, [token, user, activePage, attendanceCourse])

  useEffect(() => {
    const facultyCoursePage = user?.role === 'faculty' && ['courses', 'attendance'].includes(activePage)
    const facultyAssignmentsPage = user?.role === 'faculty' && activePage === 'assignments'
    const studentCoursePage = user?.role === 'student' && ['dashboard', 'courses'].includes(activePage)
    if (!token || !user || (!['catalog', 'courses'].includes(activePage) && !facultyCoursePage && !facultyAssignmentsPage && !studentCoursePage)) return
    let cancelled = false
    setCatalogLoading(true)
    setCatalogError('')
    const requests = [
      fetch(`${API_BASE}/catalog/specializations`, { headers: { Authorization: `Bearer ${token}` } }),
      fetch(`${API_BASE}${user.role === 'admin' ? '/admin/subjects' : user.role === 'faculty' && ['courses', 'attendance', 'assignments'].includes(activePage) ? '/faculty/subjects' : user.role === 'student' ? '/student/subjects' : '/catalog/subjects'}`, { headers: { Authorization: `Bearer ${token}` } }),
    ]
    if (user.role === 'admin') {
      requests.push(fetch(`${API_BASE}/admin/options`, { headers: { Authorization: `Bearer ${token}` } }))
      requests.push(fetch(`${API_BASE}/admin/assignments`, { headers: { Authorization: `Bearer ${token}` } }))
    }
    Promise.all(requests)
      .then(async (responses) => {
        const [specResponse, subjectResponse, optionsResponse, assignmentsResponse] = responses
        const specResult = await parseJsonResponse(specResponse)
        const subjectResult = await parseJsonResponse(subjectResponse)
        if (!specResponse.ok) throw new Error(getApiErrorMessage(specResult, 'Could not load the specialization list.'))
        if (!subjectResponse.ok) throw new Error(getApiErrorMessage(subjectResult, 'Could not load the subject list.'))
        const optionsResult = optionsResponse ? await parseJsonResponse(optionsResponse) : null
        const assignmentsResult = assignmentsResponse ? await parseJsonResponse(assignmentsResponse) : null
        if (optionsResponse && !optionsResponse.ok) throw new Error(getApiErrorMessage(optionsResult, 'Could not load admin selection options.'))
        if (assignmentsResponse && !assignmentsResponse.ok) throw new Error(getApiErrorMessage(assignmentsResult, 'Could not load faculty assignments.'))
        if (!cancelled) {
          setSpecializations(specResult.specializations || [])
          setSubjects(subjectResult.subjects || [])
          if (facultyAssignmentsPage) setClassAssignmentSubjectId((current) => current || String((subjectResult.subjects || [])[0]?.id || ''))
          if (optionsResult) {
            setAdminOptions(optionsResult)
            const mcaCourse = [...(optionsResult.courses || [])]
              .filter((course) => String(course.code || '').trim().toUpperCase() === 'MCA' || String(course.name || '').trim().toUpperCase() === 'MCA')
              .sort((a, b) => a.id - b.id)[0]
            if (mcaCourse) setSubjectCourseId(String(mcaCourse.id))
            setFacultyAssignments(assignmentsResult.assignments || [])
          }
        }
      })
      .catch((requestError) => { if (!cancelled) setCatalogError(requestError.message || 'Could not connect to the backend.') })
      .finally(() => { if (!cancelled) setCatalogLoading(false) })
    return () => { cancelled = true }
  }, [token, user, activePage])

  useEffect(() => {
    if (!token || !user || activePage !== 'assignments' || !['faculty', 'student'].includes(user.role)) return
    let cancelled = false
    setClassAssignmentsLoading(true)
    setClassAssignmentsError('')
    const endpoint = user.role === 'faculty' ? '/faculty/assignments' : '/student/assignments'
    fetch(`${API_BASE}${endpoint}`, { headers: { Authorization: `Bearer ${token}` } })
      .then(async (response) => {
        const result = await parseJsonResponse(response)
        if (!response.ok) throw new Error(getApiErrorMessage(result, 'Could not load assignments.'))
        if (!cancelled) setClassAssignments(result?.assignments || [])
      })
      .catch((requestError) => { if (!cancelled) setClassAssignmentsError(requestError.message || 'Could not connect to the backend.') })
      .finally(() => { if (!cancelled) setClassAssignmentsLoading(false) })
    return () => { cancelled = true }
  }, [token, user, activePage])

  useEffect(() => {
    if (!token || !user || (activePage !== 'calendar' && activePage !== 'dashboard' && activePage !== 'exams')) return
    let cancelled = false
    setEventsLoading(true)
    setEventsError('')
    fetch(`${API_BASE}/events`, { headers: { Authorization: `Bearer ${token}` } })
      .then(async (response) => {
        const result = await parseJsonResponse(response)
        if (!response.ok) throw new Error(getApiErrorMessage(result, 'Could not load campus events.'))
        if (!cancelled) setCampusEvents(result?.events || [])
      })
      .catch((requestError) => { if (!cancelled) setEventsError(requestError.message || 'Could not load campus events.') })
      .finally(() => { if (!cancelled) setEventsLoading(false) })
    return () => { cancelled = true }
  }, [token, user, activePage])

  useEffect(() => {
    if (user?.role !== 'student' || activePage !== 'history' || !token) return
    let cancelled = false
    setChatHistoryLoading(true)
    setChatHistoryError('')
    fetch(`${API_BASE}/student/chat-history`, { headers: { Authorization: `Bearer ${token}` } })
      .then(async (response) => {
        const result = await parseJsonResponse(response)
        if (!response.ok) throw new Error(getApiErrorMessage(result, 'Could not load your chat history.'))
        if (!cancelled) setChatHistory(result?.conversations || [])
      })
      .catch((requestError) => { if (!cancelled) setChatHistoryError(requestError.message || 'Could not load your chat history.') })
      .finally(() => { if (!cancelled) setChatHistoryLoading(false) })
    return () => { cancelled = true }
  }, [token, user, activePage])

  useEffect(() => {
    if (activePage !== 'attendance' || user?.role !== 'student' || !token) return
    let cancelled = false
    setAttendanceLoading(true)
    setAttendanceError('')
    fetch(`${API_BASE}/attendance/me`, { headers: { Authorization: `Bearer ${token}` } })
      .then(async (response) => {
        const result = await parseJsonResponse(response)
        if (!response.ok) throw new Error(getApiErrorMessage(result, 'Could not load attendance.'))
        if (!cancelled) setAttendanceSummary(result)
      })
      .catch((requestError) => { if (!cancelled) setAttendanceError(requestError.message || 'Could not load attendance.') })
      .finally(() => { if (!cancelled) setAttendanceLoading(false) })
    return () => { cancelled = true }
  }, [token, user, activePage])

  useEffect(() => {
    if (activePage === 'attendance' && user?.role === 'faculty' && roleRecords.length) {
      setAttendanceMarks(Object.fromEntries(roleRecords.map((student) => [student.id, 'present'])))
      setAttendanceMessage('')
      setAttendanceError('')
    }
  }, [activePage, roleRecords, user])

  async function logIn(event, demoAccount = null) {
    event?.preventDefault()
    if (loginLoading) return
    setLoginError('')
    setLoginLoading(true)
    try {
      const response = await fetch(`${API_BASE}/auth/login`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          username: (demoAccount?.username ?? username).trim(),
          password: demoAccount?.password ?? password,
        }),
      })
      const result = await parseJsonResponse(response)
      if (!response.ok) throw new Error(getApiErrorMessage(result, 'Login failed. Check your username and password.'))
      const profileResponse = await fetch(`${API_BASE}/auth/me`, {
        headers: { Authorization: `Bearer ${result.access_token}` },
      })
      const profile = await parseJsonResponse(profileResponse)
      if (!profileResponse.ok) throw new Error(getApiErrorMessage(profile, 'Login worked, but the account could not be loaded.'))
      const selectedRole = demoAccount?.role ?? role
      if (profile.role !== selectedRole) {
        throw new Error(`This account is registered as ${profile.role}. Choose ${profile.role} above and try again.`)
      }
      const loginUsername = (demoAccount?.username ?? username).trim()
      if (rememberUsername) localStorage.setItem(REMEMBERED_USERNAME_KEY, loginUsername)
      else localStorage.removeItem(REMEMBERED_USERNAME_KEY)
      sessionStorage.setItem(TOKEN_KEY, result.access_token)
      setToken(result.access_token)
      setUser(profile)
      setPassword('')
      setActivePage('dashboard')
    } catch (requestError) {
      setLoginError(requestError.message || 'Could not connect to CampusGPT. Check that the backend is running.')
    } finally {
      setLoginLoading(false)
    }
  }

  async function saveFacultyProfile(event) {
    event.preventDefault()
    if (profileSaving) return
    setProfileSaving(true)
    setProfileError('')
    setProfileNotice('')
    const payload = {
      full_name: facultyProfile.full_name.trim(),
      email: facultyProfile.email.trim(),
    }
    if (profileCurrentPassword || profileNewPassword) {
      payload.current_password = profileCurrentPassword
      payload.new_password = profileNewPassword
    }
    try {
      const response = await fetch(`${API_BASE}/${user.role}/profile`, {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${token}` },
        body: JSON.stringify(payload),
      })
      const result = await parseJsonResponse(response)
      if (!response.ok) throw new Error(getApiErrorMessage(result, 'Could not save your profile.'))
      setFacultyProfile((current) => ({ ...current, ...result }))
      setUser((current) => ({ ...current, ...result }))
      setProfileCurrentPassword('')
      setProfileNewPassword('')
      setProfileNotice('Your profile was updated.')
      showToast('Profile saved successfully.')
    } catch (requestError) {
      setProfileError(requestError.message || 'Could not connect to the backend.')
    } finally {
      setProfileSaving(false)
    }
  }

  function logOut() {
    sessionStorage.removeItem(TOKEN_KEY)
    setToken('')
    setUser(null)
    setPassword('')
    if (!rememberUsername) setUsername('')
    setConversation([])
    setActiveChatId(null)
    setChatHistory([])
    setActivePage('dashboard')
    setNotice('')
  }

  function startNewChat() {
    setConversation([])
    setActiveChatId(null)
    setQuestion('')
    setError('')
    setActivePage('chat')
    setNotice('')
  }

  async function openStudentChat(conversationId) {
    setOpeningChatId(conversationId)
    setChatHistoryError('')
    try {
      const response = await fetch(`${API_BASE}/student/chat-history/${conversationId}`, { headers: { Authorization: `Bearer ${token}` } })
      const result = await parseJsonResponse(response)
      if (!response.ok) throw new Error(getApiErrorMessage(result, 'Could not open this conversation.'))
      setConversation((result?.turns || []).map((turn) => ({ question: turn.question, answer: normalizeCampusGPTAnswer(turn.answer), sources: turn.sources || [] })))
      setActiveChatId(result.conversation.id)
      setQuestion('')
      setError('')
      setActivePage('chat')
      setNotice('')
    } catch (requestError) {
      setChatHistoryError(requestError.message || 'Could not open this conversation.')
    } finally {
      setOpeningChatId(null)
    }
  }

  async function deleteStudentConversation(conversationId, title = 'this conversation') {
    if (!window.confirm(`Delete "${title}"? This cannot be undone.`)) return
    setDeletingChatId(conversationId)
    setChatHistoryError('')
    try {
      const response = await fetch(`${API_BASE}/student/chat-history/${conversationId}`, { method: 'DELETE', headers: { Authorization: `Bearer ${token}` } })
      const result = await parseJsonResponse(response)
      if (!response.ok) throw new Error(getApiErrorMessage(result, 'Could not delete this conversation.'))
      setChatHistory((items) => items.filter((item) => item.id !== conversationId))
      if (activeChatId === conversationId) {
        setActiveChatId(null)
        setConversation([])
        setQuestion('')
        setError('')
      }
      showToast('Conversation deleted.')
    } catch (requestError) {
      setChatHistoryError(requestError.message || 'Could not delete this conversation.')
    } finally {
      setDeletingChatId(null)
    }
  }

  async function clearStudentChatHistory() {
    if (!chatHistory.length || !window.confirm(`Delete all ${chatHistory.length} saved conversations? This cannot be undone.`)) return
    setClearingChatHistory(true)
    setChatHistoryError('')
    try {
      const response = await fetch(`${API_BASE}/student/chat-history`, { method: 'DELETE', headers: { Authorization: `Bearer ${token}` } })
      const result = await parseJsonResponse(response)
      if (!response.ok) throw new Error(getApiErrorMessage(result, 'Could not clear your chat history.'))
      setChatHistory([])
      setActiveChatId(null)
      setConversation([])
      setQuestion('')
      setError('')
      showToast('Chat history cleared.')
    } catch (requestError) {
      setChatHistoryError(requestError.message || 'Could not clear your chat history.')
    } finally {
      setClearingChatHistory(false)
    }
  }

  async function askCampusGPT(value = question) {
    const text = value.trim()
    if (!text || loading) return
    setActivePage('chat')
    setQuestion('')
    setError('')
    const history = conversation.flatMap((item) => [
      { role: 'user', content: item.question },
      ...(item.answer ? [{ role: 'assistant', content: item.answer }] : []),
    ]).slice(-8)
    setConversation((items) => [...items, { question: text, answer: null, sources: [] }])
    setLoading(true)
    try {
      const response = await fetch(`${API_BASE}/chat`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${token}` },
        body: JSON.stringify({ question: text, history, ...(user.role === 'student' && activeChatId ? { conversation_id: activeChatId } : {}) }),
      })
      const result = await parseJsonResponse(response)
      if (!response.ok) throw new Error(getApiErrorMessage(result, 'CampusGPT could not answer right now.'))
      if (user.role === 'student' && result.conversation_id) setActiveChatId(result.conversation_id)
      setConversation((items) => items.map((item, index) => index === items.length - 1
        ? { ...item, answer: normalizeCampusGPTAnswer(result.answer), sources: result.sources || [] }
        : item))
    } catch (requestError) {
      setError(requestError.message || 'Could not connect. Check that the backend is running.')
      setConversation((items) => items.slice(0, -1))
    } finally {
      setLoading(false)
    }
  }

  async function saveSpecialization(event) {
    event.preventDefault()
    setCatalogError('')
    setCatalogNotice('')
    const editing = specializationEditId !== null
    try {
      const response = await fetch(`${API_BASE}/admin/specializations${editing ? `/${specializationEditId}` : ''}`, {
        method: editing ? 'PATCH' : 'POST',
        headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${token}` },
        body: JSON.stringify({ name: specializationName.trim() }),
      })
      const result = await parseJsonResponse(response)
      if (!response.ok) throw new Error(getApiErrorMessage(result, 'Could not save specialization.'))
      setSpecializations((items) => (editing
        ? items.map((item) => item.id === result.id ? result : item)
        : [...items, result]).sort((a, b) => a.name.localeCompare(b.name)))
      setSpecializationName('')
      setSpecializationEditId(null)
      setSpecializationFormOpen(false)
      setSpecializationListFilter('')
      setCatalogNotice(editing ? 'Specialization updated.' : 'Specialization added.')
      showToast(editing ? 'Specialization updated successfully.' : 'Specialization added successfully.')
    } catch (requestError) {
      setCatalogError(requestError.message || 'Could not connect to the backend.')
    }
  }

  async function addCourse(event) {
    event.preventDefault()
    if (courseSaving) return
    const editing = courseEditId !== null
    setCourseSaving(true)
    setCatalogError('')
    setCatalogNotice('')
    try {
      const response = await fetch(`${API_BASE}/admin/courses${editing ? `/${courseEditId}` : ''}`, {
        method: editing ? 'PATCH' : 'POST',
        headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${token}` },
        body: JSON.stringify({ name: courseName.trim(), code: courseCode.trim().toUpperCase() }),
      })
      const result = await parseJsonResponse(response)
      if (!response.ok) throw new Error(getApiErrorMessage(result, 'Could not add course.'))
      setAdminOptions((options) => ({
        ...options,
        courses: (editing ? options.courses.map((course) => course.id === result.id ? result : course) : [...options.courses, result]).sort((a, b) => a.name.localeCompare(b.name)),
      }))
      setSubjectCourseId(String(result.id))
      setCourseName('')
      setCourseCode('')
      setCourseEditId(null)
      setCourseFormOpen(false)
      setCatalogNotice(editing ? `${result.name} was updated.` : `${result.name} was added. You can now add subjects under it.`)
      showToast(editing ? `${result.name} updated successfully.` : `${result.name} added successfully.`)
    } catch (requestError) {
      setCatalogError(requestError.message || 'Could not connect to the backend.')
    } finally {
      setCourseSaving(false)
    }
  }

  async function removeCourse(course) {
    if (!window.confirm(`Remove ${course.name} (${course.code})? Its linked subjects and faculty assignments will also be removed. This cannot be undone.`)) return
    setCourseSaving(true)
    setCatalogError('')
    try {
      const response = await fetch(`${API_BASE}/admin/courses/${course.id}`, {
        method: 'DELETE',
        headers: { Authorization: `Bearer ${token}` },
      })
      const result = await parseJsonResponse(response)
      if (!response.ok) throw new Error(getApiErrorMessage(result, 'Could not remove course.'))
      const removedSubjectIds = new Set(subjects.filter((item) => String(item.course_id) === String(course.id)).map((item) => String(item.id)))
      setAdminOptions((options) => ({ ...options, courses: options.courses.filter((item) => String(item.id) !== String(course.id)) }))
      setSubjects((items) => items.filter((item) => String(item.course_id) !== String(course.id)))
      setFacultyAssignments((items) => items.filter((item) => !removedSubjectIds.has(String(item.subject_id))))
      setStudentEnrollmentRows((items) => items.filter((item) => !removedSubjectIds.has(String(item.subject_id))))
      setSubjectCourseId('')
      setCourseEditId(null)
      setCourseFormOpen(false)
      setCourseName('')
      setCourseCode('')
      setCatalogNotice(result?.message || 'Course removed.')
      showToast('Course and its linked catalog records were removed.')
    } catch (requestError) {
      setCatalogError(requestError.message || 'Could not connect to the backend.')
    } finally {
      setCourseSaving(false)
    }
  }

  async function removeSpecialization(item) {
    if (!window.confirm(`Remove specialization “${item.name}”? It must have no subjects.`)) return
    setCatalogError('')
    try {
      const response = await fetch(`${API_BASE}/admin/specializations/${item.id}`, { method: 'DELETE', headers: { Authorization: `Bearer ${token}` } })
      const result = await parseJsonResponse(response)
      if (!response.ok) throw new Error(getApiErrorMessage(result, 'Could not remove specialization.'))
      setSpecializations((items) => items.filter((current) => current.id !== item.id))
      if (subjectSpecialization === String(item.id)) setSubjectSpecialization('')
      if (specializationListFilter === String(item.id)) {
        setSpecializationListFilter('')
        setSpecializationEditId(null)
        setSpecializationName('')
        setSpecializationFormOpen(false)
      }
      setCatalogNotice('Specialization removed.')
      showToast('Specialization removed.')
    } catch (requestError) {
      setCatalogError(requestError.message || 'Could not connect to the backend.')
    }
  }

  async function addFaculty(event) {
    event.preventDefault()
    setRecordsError('')
    setRecordsLoading(true)
    setFacultySaving(true)
    try {
      const response = await fetch(`${API_BASE}/admin/faculty`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${token}` },
        body: JSON.stringify({ full_name: facultyFullName.trim(), username: facultyUsername.trim(), email: facultyEmail.trim(), password: facultyPassword }),
      })
      const result = await parseJsonResponse(response)
      if (!response.ok) throw new Error(getApiErrorMessage(result, 'Could not add faculty account.'))
      setRoleRecords((items) => [...items, result].sort((a, b) => a.full_name.localeCompare(b.full_name)))
      setRoleRecordsTotal((total) => total + 1)
      setStudentOffset(0)
      setFacultyFullName('')
      setFacultyUsername('')
      setFacultyEmail('')
      setFacultyPassword('')
      setShowFacultyInitialPassword(false)
      showToast('Faculty account created successfully.')
    } catch (requestError) {
      setRecordsError(requestError.message || 'Could not connect to the backend.')
    } finally {
      setFacultySaving(false)
      setRecordsLoading(false)
    }
  }

  function beginFacultyEdit(faculty) {
    setFacultyEditId(faculty.id)
    setFacultyEditValues({ full_name: faculty.full_name, username: faculty.username, email: faculty.email })
  }

  async function saveFacultyEdit(event) {
    event.preventDefault()
    setRecordsError('')
    try {
      const response = await fetch(`${API_BASE}/admin/faculty/${facultyEditId}`, {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${token}` },
        body: JSON.stringify(facultyEditValues),
      })
      const result = await parseJsonResponse(response)
      if (!response.ok) throw new Error(getApiErrorMessage(result, 'Could not update faculty account.'))
      setRoleRecords((items) => items.map((item) => item.id === result.id ? result : item))
      setFacultyEditId(null)
      showToast('Faculty account updated successfully.')
    } catch (requestError) {
      setRecordsError(requestError.message || 'Could not connect to the backend.')
    }
  }

  async function removeFaculty(faculty) {
    if (!window.confirm(`Remove faculty account for ${faculty.full_name}?`)) return
    setRecordsError('')
    try {
      const response = await fetch(`${API_BASE}/admin/faculty/${faculty.id}`, {
        method: 'DELETE',
        headers: { Authorization: `Bearer ${token}` },
      })
      const result = await parseJsonResponse(response)
      if (!response.ok) throw new Error(getApiErrorMessage(result, 'Could not remove faculty account.'))
      setRoleRecords((items) => items.filter((item) => item.id !== faculty.id))
      if (facultyEditId === faculty.id) setFacultyEditId(null)
      showToast('Faculty account removed.')
    } catch (requestError) {
      setRecordsError(requestError.message || 'Could not connect to the backend.')
    }
  }

  async function addStudent(event) {
    event.preventDefault()
    setRecordsError('')
    setRecordsLoading(true)
    try {
      const response = await fetch(`${API_BASE}/admin/students`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${token}` },
        body: JSON.stringify({ full_name: studentFullName.trim(), username: studentUsername.trim(), email: studentEmail.trim(), password: studentPassword }),
      })
      const result = await parseJsonResponse(response)
      if (!response.ok) throw new Error(getApiErrorMessage(result, 'Could not add student account.'))
      setRoleRecords((items) => [...items, result].sort((a, b) => a.full_name.localeCompare(b.full_name)))
      setStudentFullName('')
      setStudentUsername('')
      setStudentEmail('')
      setStudentPassword('')
      setShowStudentInitialPassword(false)
      setStudentSearch('')
      setSelectedStudentIds([])
      setNotice('Student account added.')
      showToast('Student account created successfully.')
    } catch (requestError) {
      setRecordsError(requestError.message || 'Could not connect to the backend.')
    } finally {
      setRecordsLoading(false)
    }
  }

  function beginStudentEdit(student) {
    setStudentEditId(student.id)
    setStudentEditValues({ full_name: student.full_name, username: student.username, email: student.email })
  }

  async function saveStudentEdit(event) {
    event.preventDefault()
    setRecordsError('')
    try {
      const response = await fetch(`${API_BASE}/admin/students/${studentEditId}`, {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${token}` },
        body: JSON.stringify(studentEditValues),
      })
      const result = await parseJsonResponse(response)
      if (!response.ok) throw new Error(getApiErrorMessage(result, 'Could not update student account.'))
      setRoleRecords((items) => items.map((item) => item.id === result.id ? result : item))
      setStudentEditId(null)
      setNotice('Student account updated.')
      showToast('Student account updated successfully.')
    } catch (requestError) {
      setRecordsError(requestError.message || 'Could not connect to the backend.')
    }
  }

  async function removeStudent(student) {
    if (!window.confirm(`Remove student account for ${student.full_name}?`)) return
    setRecordsError('')
    try {
      const response = await fetch(`${API_BASE}/admin/students/${student.id}`, { method: 'DELETE', headers: { Authorization: `Bearer ${token}` } })
      const result = await parseJsonResponse(response)
      if (!response.ok) throw new Error(getApiErrorMessage(result, 'Could not remove student account.'))
      setRoleRecords((items) => items.filter((item) => item.id !== student.id))
      setSelectedStudentIds((ids) => ids.filter((id) => id !== student.id))
      setRoleRecordsTotal((total) => Math.max(0, total - 1))
      if (studentEditId === student.id) setStudentEditId(null)
      setNotice(result.message || 'Student account removed.')
      showToast('Student account removed.')
    } catch (requestError) {
      setRecordsError(requestError.message || 'Could not connect to the backend.')
    }
  }

  async function removeSelectedStudents() {
    if (!selectedStudentIds.length || !window.confirm(`Remove ${selectedStudentIds.length} selected student account(s)?`)) return
    setRecordsError('')
    try {
      const response = await fetch(`${API_BASE}/admin/bulk/students`, {
        method: 'DELETE',
        headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${token}` },
        body: JSON.stringify({ ids: selectedStudentIds }),
      })
      const result = await parseJsonResponse(response)
      if (!response.ok) throw new Error(getApiErrorMessage(result, 'Could not remove the selected student accounts.'))
      setSelectedStudentIds([])
      setStudentOffset(0)
      setRoleRecordsTotal((total) => Math.max(0, total - result.deleted_count))
      setNotice(`${result.deleted_count} student account(s) removed.`)
      showToast(`${result.deleted_count} student account(s) removed.`)
    } catch (requestError) {
      setRecordsError(requestError.message || 'Could not connect to the backend.')
    }
  }

  async function saveStudentEnrollments(event) {
    event.preventDefault()
    setCatalogError('')
    setCatalogNotice('')
    if (!enrollmentStudentId || !enrollmentSubjectIds.length) {
      setCatalogError('Choose a student and at least one subject.')
      return
    }
    try {
      const response = await fetch(`${API_BASE}/admin/enrollments`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${token}` },
        body: JSON.stringify({ student_id: Number(enrollmentStudentId), subject_ids: enrollmentSubjectIds.map(Number) }),
      })
      const result = await parseJsonResponse(response)
      if (!response.ok) throw new Error(getApiErrorMessage(result, 'Could not enroll the student.'))
      setCatalogNotice(result?.message || 'Student enrollment saved.')
      showToast('Student enrollment saved successfully.')
      setEnrollmentSubjectIds([])
      const listResponse = await fetch(`${API_BASE}/admin/enrollments`, { headers: { Authorization: `Bearer ${token}` } })
      const listResult = await parseJsonResponse(listResponse)
      if (listResponse.ok) setStudentEnrollmentRows(listResult.enrollments || [])
    } catch (requestError) {
      setCatalogError(requestError.message || 'Could not connect to the backend.')
    }
  }

  async function removeStudentEnrollment(enrollment) {
    if (!window.confirm(`Remove ${enrollment.student_name} from ${enrollment.subject_name}?`)) return
    try {
      const response = await fetch(`${API_BASE}/admin/enrollments/${enrollment.id}`, { method: 'DELETE', headers: { Authorization: `Bearer ${token}` } })
      const result = await parseJsonResponse(response)
      if (!response.ok) throw new Error(getApiErrorMessage(result, 'Could not remove the enrollment.'))
      setStudentEnrollmentRows((rows) => rows.filter((row) => row.id !== enrollment.id))
      setCatalogNotice(result.message || 'Enrollment removed.')
      showToast('Student enrollment removed.')
    } catch (requestError) {
      setCatalogError(requestError.message || 'Could not connect to the backend.')
    }
  }

  async function uploadKnowledgeDocument(event) {
    event.preventDefault()
    const uploadForm = event.currentTarget
    if (!knowledgeFile || knowledgeUploadLoading) return
    setKnowledgeDocsError('')
    setKnowledgeDocsNotice('')
    if (knowledgeFile.size > 10 * 1024 * 1024) {
      setKnowledgeDocsError('Choose a file that is 10 MB or smaller.')
      return
    }
    setKnowledgeUploadLoading(true)
    try {
      const params = new URLSearchParams({ filename: knowledgeFile.name, document_type: user.role === 'admin' ? 'campus' : user.role === 'faculty' ? 'course' : documentType })
      if (user.role !== 'admin' && (user.role === 'faculty' || documentType === 'submission')) params.set('subject_id', documentSubjectId)
      const response = await fetch(`${API_BASE}/documents/upload?${params.toString()}`, {
        method: 'POST',
        headers: { Authorization: `Bearer ${token}`, 'Content-Type': 'application/octet-stream' },
        body: knowledgeFile,
      })
      const result = await parseJsonResponse(response)
      if (!response.ok) throw new Error(getApiErrorMessage(result, 'Could not upload this document.'))
      setKnowledgeDocuments((items) => [{ filename: result.filename, scope: result.scope, subject_id: user.role === 'admin' ? null : Number(documentSubjectId), can_delete: true }, ...items])
      const accessLabel = user.role === 'admin' && result.scope === 'campus' ? 'CampusGPT answers for faculty and students (file visible only to admins)' : result.scope === 'faculty' ? 'faculty' : result.scope === 'campus' ? 'campus-wide' : result.scope === 'course' ? 'subject' : result.scope === 'submission' ? 'assignment submission' : 'private'
      setKnowledgeDocsNotice(`${result.filename} is uploaded with ${accessLabel} access.`)
      showToast(`${result.filename} uploaded successfully.`)
      setKnowledgeFile(null)
      uploadForm.reset()
    } catch (requestError) {
      setKnowledgeDocsError(requestError.message || 'Could not connect to the backend.')
    } finally {
      setKnowledgeUploadLoading(false)
    }
  }

  async function removeKnowledgeDocument(document) {
    if (!window.confirm(`Remove ${document.filename} from the document library?`)) return
    setKnowledgeDocsError('')
    setKnowledgeDocsNotice('')
    try {
      const response = await fetch(`${API_BASE}/documents/${encodeURIComponent(document.filename)}`, {
        method: 'DELETE', headers: { Authorization: `Bearer ${token}` },
      })
      const result = await parseJsonResponse(response)
      if (!response.ok) throw new Error(getApiErrorMessage(result, 'Could not remove this document.'))
      setKnowledgeDocuments((items) => items.filter((item) => item.filename !== document.filename))
      setKnowledgeDocsNotice(`${document.filename} was removed.`)
      showToast('Document removed.')
    } catch (requestError) {
      setKnowledgeDocsError(requestError.message || 'Could not connect to the backend.')
    }
  }

  async function addFacultyAssignment(event) {
    event.preventDefault()
    setCatalogError('')
    setCatalogNotice('')
    if (!assignmentFacultyId || !assignmentSubjectId) {
      setCatalogError('Choose both a faculty member and a subject.')
      return
    }
    try {
      const response = await fetch(`${API_BASE}/admin/assignments`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${token}` },
        body: JSON.stringify({ faculty_id: Number(assignmentFacultyId), subject_id: Number(assignmentSubjectId) }),
      })
      const result = await parseJsonResponse(response)
      if (!response.ok) throw new Error(getApiErrorMessage(result, 'Could not assign faculty to subject.'))
      const listResponse = await fetch(`${API_BASE}/admin/assignments`, { headers: { Authorization: `Bearer ${token}` } })
      const listResult = await parseJsonResponse(listResponse)
      if (!listResponse.ok) throw new Error(getApiErrorMessage(listResult, 'Assignment saved, but the list could not be refreshed.'))
      setFacultyAssignments(listResult.assignments || [])
      setAssignmentFacultyId('')
      setCatalogNotice('Faculty assignment saved.')
      showToast('Faculty assignment saved successfully.')
    } catch (requestError) {
      setCatalogError(requestError.message || 'Could not connect to the backend.')
    }
  }

  async function removeFacultyAssignment(assignment) {
    if (!window.confirm(`Remove ${assignment.faculty_name}'s assignment to ${assignment.subject_name}?`)) return
    setCatalogError('')
    try {
      const response = await fetch(`${API_BASE}/admin/assignments/${assignment.id}`, {
        method: 'DELETE',
        headers: { Authorization: `Bearer ${token}` },
      })
      const result = await parseJsonResponse(response)
      if (!response.ok) throw new Error(getApiErrorMessage(result, 'Could not remove faculty assignment.'))
      setFacultyAssignments((items) => items.filter((item) => item.id !== assignment.id))
      setCatalogNotice('Faculty assignment removed.')
      showToast('Faculty assignment removed.')
    } catch (requestError) {
      setCatalogError(requestError.message || 'Could not connect to the backend.')
    }
  }

  async function addSubject(event) {
    event.preventDefault()
    setCatalogError('')
    setCatalogNotice('')
    if (!subjectCourseId) {
      setCatalogError('Load the MCA subject list above to set up the MCA course first.')
      return
    }
    try {
      const response = await fetch(`${API_BASE}/admin/subjects${subjectEditId ? `/${subjectEditId}` : ''}`, {
        method: subjectEditId ? 'PATCH' : 'POST',
        headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${token}` },
        body: JSON.stringify({ course_id: Number(subjectCourseId), specialization_id: subjectSpecialization ? Number(subjectSpecialization) : null, code: subjectCode.trim(), name: subjectName.trim(), semester: Number(subjectSemester), term: subjectTerm.trim() || null, instructor_name: null, section: subjectSection.trim() || null }),
      })
      const result = await parseJsonResponse(response)
      if (!response.ok) throw new Error(getApiErrorMessage(result, 'Could not add subject.'))
      const specialization = specializations.find((item) => item.id === result.specialization_id)
      const saved = { ...result, specialization_name: specialization?.name || null, course_name: adminOptions.courses.find((item) => String(item.id) === String(result.course_id))?.name || null }
      setSubjects((items) => (subjectEditId ? items.map((item) => item.id === result.id ? saved : item) : [...items, saved]).sort((a, b) => a.name.localeCompare(b.name)))
      setAdminOptions((options) => {
        const pairExists = options.term_sections.some((item) => item.term === result.term && item.section === result.section)
        return pairExists ? options : { ...options, term_sections: [...options.term_sections, { term: result.term, section: result.section }] }
      })
      setAssignmentSubjectId(String(result.id))
      setSubjectCode('')
      setSubjectName('')
      setSubjectTerm('')
      setSubjectSection('')
      setManualSubjectEntry(false)
      setAllowSubjectIdentityEdit(false)
      setCustomTerm(false)
      setCustomSection(false)
      setCatalogNotice(subjectEditId ? 'Subject updated.' : 'Subject added to the catalog.')
      showToast(subjectEditId ? 'Subject updated successfully.' : 'Subject added successfully.')
      setSubjectEditId(null)
    } catch (requestError) {
      setCatalogError(requestError.message || 'Could not connect to the backend.')
    }
  }

  function beginSubjectEdit(subject) {
    setSubjectEditId(subject.id)
    setManualSubjectEntry(false)
    setAllowSubjectIdentityEdit(false)
    const mcaCourse = [...adminOptions.courses]
      .filter((course) => String(course.code || '').trim().toUpperCase() === 'MCA' || String(course.name || '').trim().toUpperCase() === 'MCA')
      .sort((a, b) => a.id - b.id)[0]
    setSubjectCourseId(String(mcaCourse?.id || subject.course_id || ''))
    setSubjectSpecialization(subject.specialization_id ? String(subject.specialization_id) : '')
    setSubjectCode(subject.code)
    setSubjectName(subject.name)
    setSubjectSemester(String(subject.semester))
    setSubjectTerm(subject.term || '')
    setSubjectSection(subject.section || '')
    setCustomTerm(false)
    setCustomSection(false)
    document.querySelector('.catalog-form')?.scrollIntoView({ behavior: 'smooth', block: 'center' })
  }

  function startNewSubject() {
    setSubjectEditId(null)
    setManualSubjectEntry(true)
    setAllowSubjectIdentityEdit(false)
    setSubjectCode('')
    setSubjectName('')
    setSubjectSpecialization('')
    setSubjectSemester('1')
    setSubjectTerm('')
    setSubjectSection('')
    setCustomTerm(false)
    setCustomSection(false)
  }

  async function removeSubject(subject) {
    if (!window.confirm(`Remove subject “${subject.name}”?`)) return
    setCatalogError('')
    try {
      const response = await fetch(`${API_BASE}/admin/subjects/${subject.id}`, { method: 'DELETE', headers: { Authorization: `Bearer ${token}` } })
      const result = await parseJsonResponse(response)
      if (!response.ok) throw new Error(getApiErrorMessage(result, 'Could not remove subject.'))
      setSubjects((items) => items.filter((item) => item.id !== subject.id))
      setFacultyAssignments((items) => items.filter((item) => item.subject_id !== subject.id))
      setCatalogNotice('Subject removed.')
      showToast('Subject removed.')
    } catch (requestError) {
      setCatalogError(requestError.message || 'Could not connect to the backend.')
    }
  }

  async function saveCampusEvent(event) {
    event.preventDefault()
    setEventSaving(true)
    setEventsError('')
    setEventsNotice('')
    const body = {
      ...eventForm,
      title: eventForm.title.trim(),
      description: eventForm.description.trim() || null,
      location: eventForm.location.trim() || null,
      end_at: eventForm.end_at || null,
    }
    try {
      const response = await fetch(`${API_BASE}/admin/events${eventEditId ? `/${eventEditId}` : ''}`, {
        method: eventEditId ? 'PATCH' : 'POST',
        headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${token}` },
        body: JSON.stringify(body),
      })
      const result = await parseJsonResponse(response)
      if (!response.ok) throw new Error(getApiErrorMessage(result, 'Could not save the event.'))
      setCampusEvents((items) => (eventEditId ? items.map((item) => item.id === result.id ? result : item) : [...items, result]).sort((a, b) => new Date(a.start_at) - new Date(b.start_at)))
      setEventForm(emptyEventForm)
      setEventEditId(null)
      setEventsNotice(eventEditId ? 'Event updated.' : 'Event added to the campus calendar.')
      showToast(eventEditId ? 'Event updated successfully.' : 'Event added to the calendar.')
    } catch (requestError) {
      setEventsError(requestError.message || 'Could not connect to the backend.')
    } finally {
      setEventSaving(false)
    }
  }

  function beginCampusEventEdit(item) {
    setEventEditId(item.id)
    setEventForm({
      title: item.title,
      description: item.description || '',
      event_type: item.event_type,
      start_at: eventDateInput(item.start_at),
      end_at: eventDateInput(item.end_at),
      location: item.location || '',
    })
    window.scrollTo({ top: 0, behavior: 'smooth' })
  }

  async function removeCampusEvent(item) {
    if (!window.confirm(`Remove “${item.title}” from the campus calendar?`)) return
    setEventsError('')
    try {
      const response = await fetch(`${API_BASE}/admin/events/${item.id}`, { method: 'DELETE', headers: { Authorization: `Bearer ${token}` } })
      const result = await parseJsonResponse(response)
      if (!response.ok) throw new Error(getApiErrorMessage(result, 'Could not remove the event.'))
      setCampusEvents((items) => items.filter((current) => current.id !== item.id))
      setEventsNotice('Event removed from the campus calendar.')
      showToast('Event removed from the calendar.')
    } catch (requestError) {
      setEventsError(requestError.message || 'Could not connect to the backend.')
    }
  }

  async function saveAttendance(event) {
    event.preventDefault()
    if (attendanceSaving || !attendanceCourse.trim()) return
    setAttendanceSaving(true)
    setAttendanceError('')
    setAttendanceMessage('')
    try {
      const response = await fetch(`${API_BASE}/attendance/sessions`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${token}` },
        body: JSON.stringify({
          subject_id: Number(attendanceCourse),
          session_date: attendanceDate,
          records: roleRecords.map((student) => ({ student_id: student.id, status: attendanceMarks[student.id] || 'present' })),
        }),
      })
      const result = await parseJsonResponse(response)
      if (!response.ok) throw new Error(getApiErrorMessage(result, 'Could not save attendance.'))
      setAttendanceMessage(result.replaced_existing
        ? `Attendance updated for the class on ${attendanceDate}; it did not create a duplicate session.`
        : `Attendance saved for ${result.students_recorded} student accounts.`)
      showToast(result.replaced_existing ? 'Attendance updated successfully.' : 'Attendance saved successfully.')
      const subjectQuery = attendanceCourse ? `?subject_id=${encodeURIComponent(attendanceCourse)}` : ''
      const historyResponse = await fetch(`${API_BASE}/faculty/attendance${subjectQuery}`, { headers: { Authorization: `Bearer ${token}` } })
      const historyResult = await parseJsonResponse(historyResponse)
      if (historyResponse.ok) setAttendanceHistory(historyResult?.sessions || [])
    } catch (requestError) {
      setAttendanceError(requestError.message || 'Could not connect to the backend.')
    } finally {
      setAttendanceSaving(false)
    }
  }

  async function createClassAssignment(event) {
    event.preventDefault()
    if (assignmentSaving || !classAssignmentSubjectId) return
    setAssignmentSaving(true)
    setClassAssignmentsError('')
    setClassAssignmentsNotice('')
    try {
      const response = await fetch(`${API_BASE}/faculty/assignments`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${token}` },
        body: JSON.stringify({
          subject_id: Number(classAssignmentSubjectId),
          title: assignmentTitle.trim(),
          instructions: assignmentInstructions.trim(),
          due_at: new Date(assignmentDueAt).toISOString(),
        }),
      })
      const result = await parseJsonResponse(response)
      if (!response.ok) throw new Error(getApiErrorMessage(result, 'Could not create this assignment.'))
      setClassAssignments((items) => [...items, result].sort((a, b) => new Date(a.due_at) - new Date(b.due_at)))
      setAssignmentTitle('')
      setAssignmentInstructions('')
      setAssignmentDueAt('')
      setClassAssignmentsNotice('Assignment posted. Students enrolled in this subject can now see it.')
      showToast('Assignment posted successfully.')
    } catch (requestError) {
      setClassAssignmentsError(requestError.message || 'Could not connect to the backend.')
    } finally {
      setAssignmentSaving(false)
    }
  }

  async function submitClassAssignment(assignment) {
    const responseText = (studentResponses[assignment.id] ?? assignment.response_text ?? '').trim()
    const attachmentFile = studentSubmissionFiles[assignment.id]
    if ((!responseText && !attachmentFile) || submissionSavingId) return
    setSubmissionSavingId(assignment.id)
    setClassAssignmentsError('')
    setClassAssignmentsNotice('')
    try {
      let response
      if (attachmentFile) {
        const query = new URLSearchParams({ filename: attachmentFile.name, response_text: responseText })
        response = await fetch(`${API_BASE}/student/assignments/${assignment.id}/submit-file?${query}`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/octet-stream', Authorization: `Bearer ${token}` },
          body: attachmentFile,
        })
      } else {
        response = await fetch(`${API_BASE}/student/assignments/${assignment.id}/submit`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${token}` },
          body: JSON.stringify({ response_text: responseText }),
        })
      }
      const result = await parseJsonResponse(response)
      if (!response.ok) throw new Error(getApiErrorMessage(result, 'Could not submit your work.'))
      setClassAssignments((items) => items.map((item) => item.id === assignment.id ? { ...item, ...result } : item))
      setStudentSubmissionFiles((items) => ({ ...items, [assignment.id]: null }))
      setClassAssignmentsNotice('Your work was submitted successfully.')
      showToast('Your work was submitted successfully.')
    } catch (requestError) {
      setClassAssignmentsError(requestError.message || 'Could not connect to the backend.')
    } finally {
      setSubmissionSavingId(null)
    }
  }

  async function downloadSubmissionAttachment(submission) {
    try {
      const response = await fetch(`${API_BASE}/assignments/submissions/${submission.id}/attachment`, {
        headers: { Authorization: `Bearer ${token}` },
      })
      if (!response.ok) {
        const result = await parseJsonResponse(response)
        throw new Error(getApiErrorMessage(result, 'Could not download this attachment.'))
      }
      const fileUrl = URL.createObjectURL(await response.blob())
      const link = document.createElement('a')
      link.href = fileUrl
      link.download = submission.attachment_name || 'assignment-attachment'
      document.body.appendChild(link)
      link.click()
      link.remove()
      window.setTimeout(() => URL.revokeObjectURL(fileUrl), 1000)
    } catch (requestError) {
      setClassAssignmentsError(requestError.message || 'Could not download this attachment.')
    }
  }

  async function loadAssignmentSubmissions(assignment) {
    setClassAssignmentsError('')
    try {
      const response = await fetch(`${API_BASE}/faculty/assignments/${assignment.id}/submissions`, { headers: { Authorization: `Bearer ${token}` } })
      const result = await parseJsonResponse(response)
      if (!response.ok) throw new Error(getApiErrorMessage(result, 'Could not load student submissions.'))
      setSubmissionsByAssignment((items) => ({ ...items, [assignment.id]: result?.submissions || [] }))
      setSubmissionReviews((items) => {
        const next = { ...items }
        ;(result?.submissions || []).forEach((submission) => {
          next[submission.id] = { score: submission.score ?? '', feedback: submission.feedback || '' }
        })
        return next
      })
    } catch (requestError) {
      setClassAssignmentsError(requestError.message || 'Could not connect to the backend.')
    }
  }

  async function saveAssignmentReview(assignment, submission) {
    const values = submissionReviews[submission.id] || { score: submission.score ?? '', feedback: submission.feedback || '' }
    setReviewSavingId(submission.id)
    setClassAssignmentsError('')
    setClassAssignmentsNotice('')
    try {
      const response = await fetch(`${API_BASE}/faculty/assignments/${assignment.id}/submissions/${submission.id}`, {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${token}` },
        body: JSON.stringify({ score: values.score === '' ? null : Number(values.score), feedback: values.feedback.trim() || null }),
      })
      const result = await parseJsonResponse(response)
      if (!response.ok) throw new Error(getApiErrorMessage(result, 'Could not save your review.'))
      setSubmissionsByAssignment((items) => ({
        ...items,
        [assignment.id]: (items[assignment.id] || []).map((item) => item.id === submission.id ? { ...item, ...result } : item),
      }))
      setClassAssignments((items) => items.map((item) => item.id === assignment.id ? { ...item, reviewed_count: (item.reviewed_count || 0) + (submission.reviewed_at ? 0 : 1) } : item))
      setClassAssignmentsNotice(`Review saved for ${submission.student_name}.`)
      showToast(`Review saved for ${submission.student_name}.`)
    } catch (requestError) {
      setClassAssignmentsError(requestError.message || 'Could not connect to the backend.')
    } finally {
      setReviewSavingId(null)
    }
  }

  function showPreview(title) {
    setActivePage(title)
    setNotice(`${userNavigation.find((item) => item[0] === title)?.[2] || 'This section'} is a layout preview. Its academic data and actions are not connected yet.`)
  }

  function changeCalendarMonth(offset) {
    const nextMonth = new Date(calendarMonth.getFullYear(), calendarMonth.getMonth() + offset, 1)
    if (nextMonth.getFullYear() < 2026 || nextMonth.getFullYear() > 2027) return
    setCalendarMonth(nextMonth)
    setSelectedCalendarDate(`${nextMonth.getFullYear()}-${String(nextMonth.getMonth() + 1).padStart(2, '0')}-01`)
  }

  function changeCalendarYear(year) {
    const nextYear = Number(year)
    setCalendarMonth(new Date(nextYear, calendarMonth.getMonth(), 1))
    setSelectedCalendarDate(`${nextYear}-${String(calendarMonth.getMonth() + 1).padStart(2, '0')}-01`)
  }

  if (checkingSession) return <div className="auth-loading">Checking your login…</div>
  if (!token || !user) {
    return (
      <main className="login-page">
        <section className="login-card">
          <div className="login-brand"><img src={allianceMcaLogo} alt="Alliance University MCA" style={{ height: 54, width: 'auto', objectFit: 'contain' }} /><span><strong>MCA CampusGPT</strong><small>YOUR ACADEMIC LEARNING SPACE</small></span></div>
          <span className="eyebrow">WELCOME BACK</span>
          <h1>Sign in to your campus</h1>
          <p className="login-intro">Choose your account type, then use the username and password you registered.</p>
          <div className="demo-login" aria-label="Demo sign-in options">
            <span>Quick demo sign-in</span>
            <div>{DEMO_ACCOUNTS.map((account) => <button type="button" key={account.role} disabled={loginLoading} onClick={() => logIn(null, account)}>{loginLoading ? 'Signing in…' : account.label}</button>)}</div>
          </div>
          <div className="role-choices" aria-label="Account type">
            {roles.map((item) => <button type="button" key={item.value} className={role === item.value ? 'role-choice selected' : 'role-choice'} onClick={() => { setRole(item.value); setLoginError('') }}>{item.label}</button>)}
          </div>
          <form className="login-form" autoComplete="on" onSubmit={logIn}>
            <label>Username<input name="username" autoComplete="username" value={username} onChange={(event) => setUsername(event.target.value)} placeholder="Enter your registered username" required /></label>
            <label>Password<span className="password-input-wrap"><input name="password" type={showPassword ? 'text' : 'password'} autoComplete="current-password" value={password} onChange={(event) => setPassword(event.target.value)} placeholder="Enter your password" required /><button className="password-visibility" type="button" aria-label={showPassword ? 'Hide password' : 'Show password'} aria-pressed={showPassword} onClick={() => setShowPassword((visible) => !visible)}><svg aria-hidden="true" viewBox="0 0 24 24" fill="none"><path d="M2.5 12s3.4-6 9.5-6 9.5 6 9.5 6-3.4 6-9.5 6-9.5-6-9.5-6Z" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round"/><circle cx="12" cy="12" r="2.7" stroke="currentColor" strokeWidth="1.7"/>{!showPassword && <path d="m4 4 16 16" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round"/>}</svg></button></span></label>
            <label className="remember-username"><input type="checkbox" checked={rememberUsername} onChange={(event) => { setRememberUsername(event.target.checked); if (!event.target.checked) localStorage.removeItem(REMEMBERED_USERNAME_KEY) }} />Remember my username on this device</label>
            {loginError && <p className="login-error" role="alert">{loginError}</p>}
            <button className="login-submit" type="submit" disabled={loginLoading}>{loginLoading ? 'Signing in…' : `Sign in as ${roles.find((item) => item.value === role)?.label}`}</button>
          </form>
          <p className="login-help">Your username can be remembered on this device. After signing in, choose Save in your browser’s prompt to autofill the password next time.</p>
        </section>
      </main>
    )
  }

  const isChat = activePage === 'chat'
  const userNavigation = roleNavigation[user.role] || roleNavigation.student
  const currentLabel = userNavigation.find((item) => item[0] === activePage)?.[2] || 'Dashboard'
  const filteredSubjects = subjects.filter((subject) => {
    const matchesText = `${subject.code} ${subject.name} ${subject.specialization_name || ''} ${subject.instructor_name || ''} ${subject.term || ''}`.toLowerCase().includes(subjectSearch.trim().toLowerCase())
    const matchesSpecialization = !specializationFilter || String(subject.specialization_id) === specializationFilter
    return matchesText && matchesSpecialization
  })
  const upcomingCampusEvents = campusEvents.filter((item) => new Date(item.start_at) >= new Date()).slice(0, 2)
  const examEvents = campusEvents.filter((item) => item.event_type === 'exam').sort((a, b) => new Date(a.start_at) - new Date(b.start_at))
  const studentSemesters = [...new Set(subjects.map((subject) => Number(subject.semester)).filter(Number.isFinite))].sort((a, b) => a - b)
  const calendarYear = calendarMonth.getFullYear()
  const calendarMonthIndex = calendarMonth.getMonth()
  const calendarFirstWeekday = new Date(calendarYear, calendarMonthIndex, 1).getDay()
  const calendarDayCount = new Date(calendarYear, calendarMonthIndex + 1, 0).getDate()
  const calendarCellCount = Math.ceil((calendarFirstWeekday + calendarDayCount) / 7) * 7
  const calendarEventDays = new Map()
  campusEvents.forEach((item) => {
    const dateKey = campusDateKey(item.start_at)
    calendarEventDays.set(dateKey, [...(calendarEventDays.get(dateKey) || []), item])
  })
  const calendarCells = Array.from({ length: calendarCellCount }, (_, index) => {
    const day = index - calendarFirstWeekday + 1
    if (day < 1 || day > calendarDayCount) return null
    const dateKey = `${calendarYear}-${String(calendarMonthIndex + 1).padStart(2, '0')}-${String(day).padStart(2, '0')}`
    return { day, dateKey, events: calendarEventDays.get(dateKey) || [] }
  })
  const selectedCalendarEvents = campusEvents.filter((item) => campusDateKey(item.start_at) === selectedCalendarDate)
  const selectedCalendarLabel = new Intl.DateTimeFormat('en-IN', { timeZone: 'Asia/Kolkata', dateStyle: 'full' }).format(new Date(`${selectedCalendarDate}T12:00:00+05:30`))
  const mcaCourse = [...adminOptions.courses]
    .filter((course) => course.is_active !== false && (String(course.code || '').trim().toUpperCase() === 'MCA' || String(course.name || '').trim().toUpperCase() === 'MCA'))
    .sort((a, b) => a.id - b.id)[0]
  const courseOptions = mcaCourse ? [{ value: String(mcaCourse.id), label: 'MCA' }] : []
  const existingSubjectOptions = [
    ...subjects.map((item) => ({ value: String(item.id), label: `${item.name} · ${item.code} · Semester ${item.semester}` })),
    { value: '__new_subject__', label: '+ Add a new subject' },
  ]
  const specializationOptions = [{ value: '', label: 'Not specified yet' }, ...specializations.map((item) => ({ value: String(item.id), label: item.name }))]
  const facultyOptions = adminOptions.faculty.map((item) => ({ value: String(item.id), label: `${item.full_name} · ${item.username}` }))
  const assignmentSubjectOptions = subjects.map((item) => ({ value: String(item.id), label: `${item.code} · ${item.name} · Semester ${item.semester}` }))
  const termOptions = [...new Set(adminOptions.term_sections.map((item) => item.term).filter(Boolean))]
  const sectionOptions = [...new Set(adminOptions.term_sections.map((item) => item.section).filter(Boolean))]
  const displayName = user.full_name || user.username
  const initial = displayName.charAt(0).toUpperCase()
  const roleLabel = roles.find((item) => item.value === user.role)?.label || user.role

  return (
    <div className="campus-shell">
      <aside className="sidebar">
        <button className="brand" onClick={() => { setActivePage('dashboard'); setNotice('') }}>
          <img src={allianceMcaLogo} alt="Alliance University MCA" style={{ height: 64, width: 'auto', objectFit: 'contain' }} />
          <span><strong>MCA CampusGPT</strong><small>ACADEMIC LEARNING SPACE</small></span>
        </button>
        <div className="nav-caption">{roleLabel.toUpperCase()} SPACE</div>
        <nav aria-label={`${roleLabel} navigation`}>
          {userNavigation.map(([id, icon, label]) => (
            <button key={id} className={`nav-item ${activePage === id ? 'selected' : ''}`} onClick={() => (['dashboard', 'documents', 'chat', 'assignments', 'courses', 'calendar', 'exams', 'attendance', 'history', 'catalog', 'admin-faculty', 'admin-users', 'faculty-students'].includes(id) || (id === 'profile' && ['student', 'faculty'].includes(user.role))) ? (setActivePage(id), setNotice('')) : showPreview(id)}>
              <span className="nav-icon">{icon}</span><span>{label}</span>
              {id === 'chat' && <span className="new-pill">AI</span>}
            </button>
          ))}
        </nav>
        <div className="sidebar-bottom">
          <div className="help-card"><span className="help-spark">✦</span><strong>Need a hand?</strong><p>Ask your academic assistant about MCA courses and resources.</p><button onClick={() => { setActivePage('chat'); setNotice('') }}>Ask CampusGPT ↗</button></div>
          <div className="user-profile"><span className="avatar">{initial}</span><span><strong>{displayName}</strong><small>MCA {roleLabel}</small></span></div>
        </div>
      </aside>

      <main className="main-area">
        <header className="topbar">
          <label className="global-search"><span>⌕</span><input placeholder="Search courses, documents…" aria-label="Search" /></label>
          <div className="top-actions"><button className="notification-button" aria-label="Notifications">♧<i /></button><span className="top-avatar">{initial}</span><span className="header-name">{displayName}⌄</span><button className="logout-button" onClick={logOut}>Sign out</button></div>
        </header>

        {toast && <div className={`save-toast ${toast.type === 'error' ? 'save-toast-error' : ''}`} role={toast.type === 'error' ? 'alert' : 'status'} aria-live={toast.type === 'error' ? 'assertive' : 'polite'}>
          <span className="save-toast-icon" aria-hidden="true">{toast.type === 'error' ? '!' : '✓'}</span>
          <span className="save-toast-copy"><strong>{toast.type === 'error' ? 'Could not save' : 'Saved successfully'}</strong><span>{toast.message}</span></span>
          <button type="button" aria-label="Dismiss notification" onClick={() => setToast(null)}>×</button>
        </div>}

        {activePage === 'dashboard' && user.role === 'student' ? (
          <section className="dashboard-page">
            <div className="welcome-line"><div><span className="eyebrow">YOUR MCA LEARNING SPACE</span><h1>Good morning, {displayName} <span>👋</span></h1><p>Here’s what’s happening with your studies.</p></div><div className="term-chip"><span className="term-dot" /> MCA{studentSemesters.length ? ` · Semester ${studentSemesters.join(', ')}` : ''}</div></div>

            <section className="assistant-card">
              <div className="assistant-copy"><span className="hero-label">✳ &nbsp;YOUR ACADEMIC ASSISTANT</span><h2>Ask MCA CampusGPT</h2><p>Ask anything about your MCA courses and campus resources.</p>
                <form className="dashboard-ask" onSubmit={(event) => { event.preventDefault(); askCampusGPT() }}><input value={question} onChange={(event) => setQuestion(event.target.value)} placeholder="Ask anything about MCA…" aria-label="Ask MCA CampusGPT"/><button aria-label="Send question" disabled={!question.trim()}>⌕</button></form>
                <div className="suggested-questions">Try: <button type="button" onClick={() => askCampusGPT(suggestions[0])}>{suggestions[0]}</button></div>
              </div><div className="assistant-orbit"><span>✳</span></div>
            </section>

            <section className="content-section"><div className="section-heading"><div><span className="eyebrow">YOUR ENROLLMENT</span><h2>My Courses</h2></div><button className="text-action" onClick={() => { setActivePage('courses'); setNotice('') }}>View my courses <span>→</span></button></div>
              {catalogLoading ? <div className="role-list-message">Loading your enrolled subjects…</div> : subjects.length === 0 ? <div className="role-list-message">No subjects are linked to your student account yet. Ask Admin to enroll you.</div> : <div className="course-grid">{subjects.slice(0, 3).map((course, index) => <article className="course-card" key={course.id}><div className="course-top"><span className={`course-icon course-tone-${index % 3}`}>{['⌘', '✳', '⌁'][index % 3]}</span><span className="course-code">{course.term || `Semester ${course.semester}`}</span></div><h3>{course.name}</h3><p>{course.code}{course.instructor_name ? ` · ${course.instructor_name}` : ''}</p><div className="course-actions"><button onClick={() => { setActivePage('courses'); setNotice('') }}>Open course</button><button onClick={() => askCampusGPT(`Help me with ${course.name} (${course.code})`)}>Ask AI</button></div></article>)}</div>}
            </section>

            <section className="content-section upcoming-section"><div className="section-heading"><div><span className="eyebrow">PLAN AHEAD</span><h2>Upcoming campus events</h2></div><button className="text-action" onClick={() => { setActivePage('calendar'); setNotice('') }}>Open calendar <span>→</span></button></div>
              {eventsError && <div className="error-note" role="alert">{eventsError}</div>}
              {eventsLoading ? <div className="role-list-message">Loading campus events…</div> : upcomingCampusEvents.length === 0 ? <div className="role-list-message">No upcoming campus events have been added.</div> : <div className="upcoming-grid">{upcomingCampusEvents.map((item) => { const badge = eventDateBadge(item.start_at); return <article className="event-card" key={item.id}><span className={`event-date ${item.event_type === 'exam' ? 'exam-date' : 'assignment-date'}`}><small>{badge.month}</small><strong>{badge.day}</strong></span><span><strong>{item.title}</strong><small>{item.event_type} · {eventDateTime(item.start_at)}{item.location ? ` · ${item.location}` : ''}</small></span><span className="event-arrow">→</span></article> })}</div>}
            </section>
            <p className="demo-note">Campus events are posted by an admin. Confirm important dates with official university notices.</p>
          </section>
        ) : activePage === 'dashboard' && user.role === 'faculty' ? (
          <section className="dashboard-page role-dashboard">
            <div className="welcome-line"><div><span className="eyebrow">FACULTY WORKSPACE</span><h1>Welcome, {displayName} <span>👋</span></h1><p>Your teaching tools and class overview.</p></div><div className="term-chip"><span className="term-dot" /> Faculty account</div></div>
            <section className="role-hero faculty-hero"><span className="role-hero-icon">▤</span><div><span className="eyebrow">TEACHING ASSISTANT</span><h2>Plan and support your MCA classes</h2><p>Ask CampusGPT about course material or open your student roster.</p></div><button className="role-primary" onClick={() => { setActivePage('chat'); setNotice('') }}>Ask CampusGPT ↗</button></section>
            <div className="role-card-grid">
              <button className="role-card" onClick={() => { setActivePage('courses'); setNotice('') }}><span className="role-card-icon">▤</span><strong>My Courses</strong><small>See the MCA subjects assigned to you and upload course notes.</small><span className="role-card-link">Open my courses →</span></button>
              <button className="role-card" onClick={() => { setActivePage('faculty-students'); setNotice('') }}><span className="role-card-icon">♙</span><strong>Student Roster</strong><small>View students enrolled in your subjects.</small><span className="role-card-link">View students →</span></button>
              <button className="role-card" onClick={() => { setActivePage('assignments'); setNotice('') }}><span className="role-card-icon">▧</span><strong>Assignments</strong><small>Create and review class assignments.</small><span className="role-card-link">Open assignments →</span></button>
              <button className="role-card" onClick={() => { setActivePage('attendance'); setNotice('') }}><span className="role-card-icon">◷</span><strong>Attendance</strong><small>Record attendance for a class.</small><span className="role-card-link">Record attendance →</span></button>
            </div>
            <p className="demo-note">Your courses and attendance tools use the academic data maintained by Admin.</p>
          </section>
        ) : activePage === 'dashboard' && user.role === 'admin' ? (
          <section className="dashboard-page role-dashboard">
            <div className="welcome-line"><div><span className="eyebrow">ADMINISTRATION</span><h1>Welcome, {displayName} <span>👋</span></h1><p>Manage CampusGPT accounts and system resources.</p></div><div className="term-chip"><span className="term-dot" /> Admin account</div></div>
            <section className="role-hero admin-hero"><span className="role-hero-icon">⚙</span><div><span className="eyebrow">CAMPUSGPT CONTROL CENTER</span><h2>Manage your MCA CampusGPT workspace</h2><p>Add and maintain faculty accounts, users, subjects, and specializations.</p></div><button className="role-primary" onClick={() => { setActivePage('admin-faculty'); setNotice('') }}>Manage faculty ↗</button></section>
            <div className="admin-count-grid" aria-label="Campus totals">
              {[['Students', adminSummary.students], ['Faculty', adminSummary.faculty], ['MCA course', adminSummary.courses], ['Subjects', adminSummary.subjects]].map(([label, count]) => <article className="admin-count-card" key={label}><span>{label}</span><strong>{count}</strong></article>)}
            </div>
            <div className="role-card-grid">
              <button className="role-card" onClick={() => { setActivePage('admin-faculty'); setNotice('') }}><span className="role-card-icon">♙</span><strong>Faculty Management</strong><small>Add faculty accounts, update their details, or remove an account.</small><span className="role-card-link">Manage faculty →</span></button>
              <button className="role-card" onClick={() => { setActivePage('admin-users'); setNotice('') }}><span className="role-card-icon">♙</span><strong>Student Management</strong><small>Create student accounts, edit details, and remove accounts.</small><span className="role-card-link">Manage students →</span></button>
              <button className="role-card" onClick={() => { setActivePage('catalog'); setNotice('') }}><span className="role-card-icon">▤</span><strong>MCA Catalog</strong><small>Manage MCA subjects, specializations, faculty assignments, and student enrollment.</small><span className="role-card-link">Manage catalog →</span></button>
              <button className="role-card" onClick={() => { setActivePage('documents'); setNotice('') }}><span className="role-card-icon">▧</span><strong>Knowledge Documents</strong><small>Upload PDF, Word, text, and Markdown course materials.</small><span className="role-card-link">Manage documents →</span></button>
              <button className="role-card" onClick={() => { setActivePage('chat'); setNotice('') }}><span className="role-card-icon">✳</span><strong>Test CampusGPT</strong><small>Try the academic assistant.</small><span className="role-card-link">Open assistant →</span></button>
            </div>
            <p className="demo-note">Use the catalog to enroll students in their subjects. Document visibility follows each uploader’s role and subject access.</p>
          </section>
        ) : activePage === 'documents' ? (
          <section className="role-list-page knowledge-documents-page">
            <span className="eyebrow">{user.role.toUpperCase()} · DOCUMENTS</span>
            <h1>{user.role === 'admin' ? 'Campus knowledge documents' : user.role === 'faculty' ? 'My course documents' : 'My documents'}</h1>
            <p>{user.role === 'admin' ? 'Upload official college information here. CampusGPT can use it to answer faculty and student questions, but only admins can see the uploaded files and file names.' : user.role === 'faculty' ? 'Upload notes to a subject you teach. Enrolled students and faculty assigned to that subject can use them; admins can see faculty uploads.' : 'Notes shared for your enrolled subjects appear here. Your personal notes stay private; assignment submissions are shared with the faculty assigned to that subject. Ask CampusGPT about college policies or fees.'}</p>
            {knowledgeDocsNotice && <div className="success-note" role="status">{knowledgeDocsNotice}</div>}
            {knowledgeDocsError && <div className="error-note" role="alert">{knowledgeDocsError}</div>}
            <form className="catalog-form knowledge-upload-form" onSubmit={uploadKnowledgeDocument}>
              <h2>{user.role === 'admin' ? 'Upload a college document' : user.role === 'faculty' ? 'Upload subject notes' : 'Upload notes or assignment work'}</h2>
              {user.role === 'student' && <label>Document purpose<select value={documentType} onChange={(event) => setDocumentType(event.target.value)}><option value="personal">Private study notes</option><option value="submission">Assignment submission for faculty</option></select></label>}
              {user.role === 'faculty' && <SearchableSelect label="Subject" required value={documentSubjectId} options={documentSubjects.map((subject) => ({ value: String(subject.id), label: `${subject.name} · ${subject.code}` }))} onChange={setDocumentSubjectId} placeholder="Search your assigned subjects…" emptyMessage="No subjects are assigned to your account yet." />}
              {user.role === 'student' && documentType === 'submission' && <SearchableSelect label="Submission subject" required value={documentSubjectId} options={documentSubjects.map((subject) => ({ value: String(subject.id), label: `${subject.name} · ${subject.code}` }))} onChange={setDocumentSubjectId} placeholder="Search your enrolled subjects…" emptyMessage="No subjects are enrolled for your account yet. Ask Admin to enroll you." />}
              <label>Choose a PDF, Word document, or text file<input type="file" accept=".pdf,.docx,.txt,.md,application/pdf,application/vnd.openxmlformats-officedocument.wordprocessingml.document,text/plain,text/markdown" onChange={(event) => { setKnowledgeFile(event.target.files?.[0] || null); setKnowledgeDocsError(''); setKnowledgeDocsNotice('') }} required /></label>
              <small>Supported: PDF, Word (.docx), text (.txt), and Markdown (.md). Maximum 10 MB. Scanned PDFs need OCR to be readable.</small>
              <button className="login-submit" type="submit" disabled={knowledgeUploadLoading || !knowledgeFile || ((user.role === 'faculty' || (user.role === 'student' && documentType === 'submission')) && !documentSubjectId)}>{knowledgeUploadLoading ? 'Uploading…' : 'Upload document'}</button>
            </form>
            <div className="catalog-table-heading"><h2>Uploaded documents</h2><span>{knowledgeDocuments.length} total</span></div>
            {knowledgeDocsLoading ? <div className="role-list-message">Loading documents…</div> : knowledgeDocuments.length === 0 ? <div className="role-list-message">No documents are available here yet.</div> : <div className="role-table-wrap"><table className="role-table"><thead><tr><th>File name</th><th>Access</th><th>Subject</th><th>Uploaded by</th><th>Action</th></tr></thead><tbody>{knowledgeDocuments.map((document) => <tr key={document.id || document.filename}><td>{document.filename}</td><td>{document.scope === 'faculty' ? 'Admin + faculty' : document.scope === 'campus' ? 'Campus-wide' : document.scope === 'course' ? 'Subject notes' : document.scope === 'submission' ? 'Assignment submission' : 'Private notes'}</td><td>{document.subject_name || '—'}</td><td>{document.uploader_name || (['campus', 'faculty'].includes(document.scope) ? 'Admin' : 'You')}</td><td>{document.can_delete && <button type="button" className="text-action destructive-action" onClick={() => removeKnowledgeDocument(document)}>Remove</button>}</td></tr>)}</tbody></table></div>}
            <button className="back-button" onClick={() => { setActivePage('dashboard'); setNotice('') }}>← Back to Dashboard</button>
          </section>
        ) : activePage === 'profile' && ['student', 'faculty'].includes(user.role) ? (
          <section className="role-list-page profile-page">
            <span className="eyebrow">{user.role.toUpperCase()} WORKSPACE</span><h1>My profile</h1>
            <p>Your existing name and email are filled in below. Edit them only if they change. Your username, role, and {user.role === 'faculty' ? 'teaching assignments' : 'course enrollments'} are managed by Admin.</p>
            {profileNotice && <div className="success-note" role="status">{profileNotice}</div>}
            {profileError && <div className="error-note" role="alert">{profileError}</div>}
            {profileLoading ? <div className="role-list-message">Loading your profile…</div> : <form className="catalog-form faculty-profile-form" onSubmit={saveFacultyProfile}>
              <label>Full name<input value={facultyProfile.full_name} onChange={(event) => setFacultyProfile((item) => ({ ...item, full_name: event.target.value }))} required minLength="1" maxLength="120" /></label>
              <label>Email address<input type="email" autoComplete="email" value={facultyProfile.email} onChange={(event) => setFacultyProfile((item) => ({ ...item, email: event.target.value }))} required maxLength="255" /></label>
              <label>Username<input value={user.username || facultyProfile.username || ''} readOnly aria-readonly="true" /></label>
              <label>Role<input value={user.role === 'faculty' ? 'Faculty' : 'Student'} readOnly aria-readonly="true" /></label>
              <div className="profile-password-heading"><h2>Change password (optional)</h2><small>Leave both password fields blank to keep your current password.</small></div>
              <label>Current password<input type="password" autoComplete="current-password" value={profileCurrentPassword} onChange={(event) => setProfileCurrentPassword(event.target.value)} minLength="8" maxLength="128" /></label>
              <label>New password<input type="password" autoComplete="new-password" value={profileNewPassword} onChange={(event) => setProfileNewPassword(event.target.value)} minLength="8" maxLength="128" /></label>
              <button className="login-submit" type="submit" disabled={profileSaving}>{profileSaving ? 'Saving…' : 'Save profile'}</button>
            </form>}
            <button className="back-button" onClick={() => { setActivePage('dashboard'); setNotice('') }}>← Back to {user.role === 'faculty' ? 'Faculty' : 'Student'} Home</button>
          </section>
        ) : activePage === 'assignments' && user.role === 'faculty' ? (
          <section className="role-list-page assignments-page">
            <span className="eyebrow">FACULTY WORKSPACE</span><h1>Class assignments</h1>
            <p>Create work for a subject you teach, then review student responses.</p>
            {classAssignmentsNotice && <div className="success-note" role="status">{classAssignmentsNotice}</div>}
            {classAssignmentsError && <div className="error-note" role="alert">{classAssignmentsError}</div>}
            <form className="catalog-form" onSubmit={createClassAssignment}>
              <h2>Post an assignment</h2>
              <SearchableSelect label="Subject" required value={classAssignmentSubjectId} options={subjects.map((subject) => ({ value: String(subject.id), label: `${subject.name} · ${subject.code}` }))} onChange={setClassAssignmentSubjectId} placeholder="Search your assigned subjects…" emptyMessage="No subjects are assigned to your account." />
              <label>Assignment title<input value={assignmentTitle} onChange={(event) => setAssignmentTitle(event.target.value)} placeholder="e.g., Python variables and data types" required minLength="3" maxLength="180" /></label>
              <label>Due date and time<input type="datetime-local" value={assignmentDueAt} onChange={(event) => setAssignmentDueAt(event.target.value)} required /></label>
              <label>Instructions<textarea value={assignmentInstructions} onChange={(event) => setAssignmentInstructions(event.target.value)} placeholder="Explain what students should complete and submit." required minLength="5" maxLength="10000" rows="5" /></label>
              <button className="login-submit" type="submit" disabled={assignmentSaving || !classAssignmentSubjectId}>{assignmentSaving ? 'Posting…' : 'Post assignment'}</button>
            </form>
            <div className="catalog-table-heading"><h2>Assignments you posted</h2><span>{classAssignments.length} total</span></div>
            {classAssignmentsLoading ? <div className="role-list-message">Loading assignments…</div> : classAssignments.length === 0 ? <div className="role-list-message">No assignments yet. Use the form above to post the first one.</div> : <div className="campus-event-list">{classAssignments.map((assignment) => <article className="campus-event-card assignment-item" key={assignment.id}>
              <div className="campus-event-details"><span className="role-badge">{assignment.subject_name}</span><h2>{assignment.title}</h2><p>Due {new Date(assignment.due_at).toLocaleString()}</p><p className="campus-event-description">{assignment.instructions}</p><small>{assignment.submission_count || 0} submitted · {assignment.reviewed_count || 0} reviewed</small>
                <button className="text-action" type="button" onClick={() => loadAssignmentSubmissions(assignment)}>{Object.prototype.hasOwnProperty.call(submissionsByAssignment, assignment.id) ? 'Refresh submissions' : 'View submissions'}</button>
              </div>
              {Object.prototype.hasOwnProperty.call(submissionsByAssignment, assignment.id) && <div className="assignment-submissions">{submissionsByAssignment[assignment.id].length === 0 ? <p>No students have submitted work yet.</p> : submissionsByAssignment[assignment.id].map((submission) => <article className="assignment-submission" key={submission.id}>
                <h3>{submission.student_name} <small>· {submission.username}</small></h3><small>Submitted {new Date(submission.submitted_at).toLocaleString()}</small>{submission.response_text && <p className="submission-response">{submission.response_text}</p>}{submission.attachment_name && <button type="button" className="text-action" onClick={() => downloadSubmissionAttachment(submission)}>Download {submission.attachment_name}</button>}
                <label>Score (0–100)<input type="number" min="0" max="100" step="0.5" value={submissionReviews[submission.id]?.score ?? submission.score ?? ''} onChange={(event) => setSubmissionReviews((items) => ({ ...items, [submission.id]: { score: event.target.value, feedback: items[submission.id]?.feedback ?? submission.feedback ?? '' } }))} /></label>
                <label>Feedback<textarea rows="2" maxLength="4000" value={submissionReviews[submission.id]?.feedback ?? submission.feedback ?? ''} onChange={(event) => setSubmissionReviews((items) => ({ ...items, [submission.id]: { score: items[submission.id]?.score ?? submission.score ?? '', feedback: event.target.value } }))} placeholder="Share feedback for the student" /></label>
                <button type="button" className="text-action" disabled={reviewSavingId === submission.id} onClick={() => saveAssignmentReview(assignment, submission)}>{reviewSavingId === submission.id ? 'Saving…' : 'Save review'}</button>
              </article>)}</div>}
            </article>)}</div>}
            <button className="back-button" onClick={() => { setActivePage('dashboard'); setNotice('') }}>← Back to Faculty Home</button>
          </section>
        ) : activePage === 'assignments' && user.role === 'student' ? (
          <section className="role-list-page assignments-page">
            <span className="eyebrow">STUDENT SPACE</span><h1>My assignments</h1><p>Assignments posted by faculty for your enrolled subjects.</p>
            {classAssignmentsNotice && <div className="success-note" role="status">{classAssignmentsNotice}</div>}
            {classAssignmentsError && <div className="error-note" role="alert">{classAssignmentsError}</div>}
            {classAssignmentsLoading ? <div className="role-list-message">Loading assignments…</div> : classAssignments.length === 0 ? <div className="role-list-message">No assignments have been posted for your enrolled subjects yet.</div> : <div className="campus-event-list">{classAssignments.map((assignment) => <article className="campus-event-card assignment-item" key={assignment.id}>
              <div className="campus-event-details"><span className="role-badge">{assignment.subject_name}</span><h2>{assignment.title}</h2><p>Due {new Date(assignment.due_at).toLocaleString()}</p><p className="campus-event-description">{assignment.instructions}</p>
                {assignment.reviewed_at && <div className="success-note">Faculty review: {assignment.score === null ? 'No score entered' : `${assignment.score}/100`}{assignment.feedback ? ` · ${assignment.feedback}` : ''}</div>}
                {assignment.submitted_at && !assignment.reviewed_at && <p className="role-badge">Submitted {new Date(assignment.submitted_at).toLocaleString()}</p>}
                <label>Your response (optional if you attach a file)<textarea rows="5" maxLength="20000" value={studentResponses[assignment.id] ?? assignment.response_text ?? ''} onChange={(event) => setStudentResponses((items) => ({ ...items, [assignment.id]: event.target.value }))} placeholder="Type your answer or work here…" /></label>
                <label>Attach your work (optional)<input key={assignment.submitted_at || 'new'} type="file" accept=".pdf,.docx,.txt,.md,.py,.java,.js,.jsx,.html,.css,.zip,.png,.jpg,.jpeg" onChange={(event) => setStudentSubmissionFiles((items) => ({ ...items, [assignment.id]: event.target.files?.[0] || null }))} /><small>PDF, Word, text, code, image, or ZIP · maximum 10 MB{assignment.attachment_name ? ` · Current file: ${assignment.attachment_name}` : ''}</small></label>
                {assignment.submission_id && assignment.attachment_name && <button type="button" className="text-action" onClick={() => downloadSubmissionAttachment(assignment)}>Download my attached file</button>}
                <button type="button" className="login-submit" disabled={submissionSavingId === assignment.id || (!(studentResponses[assignment.id] ?? assignment.response_text ?? '').trim() && !studentSubmissionFiles[assignment.id])} onClick={() => submitClassAssignment(assignment)}>{submissionSavingId === assignment.id ? 'Submitting…' : assignment.submitted_at ? 'Resubmit work' : 'Submit work'}</button>
              </div>
            </article>)}</div>}
            <button className="back-button" onClick={() => { setActivePage('dashboard'); setNotice('') }}>← Back to Student Home</button>
          </section>
        ) : activePage === 'catalog' && user.role === 'admin' ? (
          <section className="role-list-page catalog-page">
            <span className="eyebrow">ADMINISTRATION</span><h1>MCA subjects and specializations</h1><p>Manage the MCA subject list, specializations, faculty assignments, and student enrollment.</p>
            {catalogNotice && <div className="success-note" role="status">{catalogNotice}</div>}
            {catalogError && <div className="error-note" role="alert">{catalogError}</div>}
            <div className="catalog-form-grid">
              <form className="catalog-form" onSubmit={addSubject}>
                <h2>{subjectEditId ? 'Edit subject' : manualSubjectEntry ? 'Add a new subject' : 'Select a subject'}</h2>
                {!subjectEditId && !manualSubjectEntry && <button type="button" className="catalog-select-button" onClick={startNewSubject}>＋ Add a new subject and code</button>}
                <SearchableSelect label="Subject" required={!manualSubjectEntry} value={manualSubjectEntry ? '__new_subject__' : subjectEditId ? String(subjectEditId) : ''} options={existingSubjectOptions} onChange={(value) => { if (value === '__new_subject__') startNewSubject(); else { const existingSubject = subjects.find((item) => String(item.id) === String(value)); if (existingSubject) beginSubjectEdit(existingSubject) } }} placeholder="Type a few letters of the subject name or code…" emptyMessage="No subjects are in the catalog yet." />
                <small>{manualSubjectEntry ? 'Enter a code and name only for a subject that is not already listed.' : subjectEditId ? 'The selected subject’s saved code and name are shown below. You can change its term and semester without retyping them.' : 'Search and select an existing subject. Its saved name and code will fill in automatically. Choose “+ Add a new subject” only if it is not listed.'}</small>
                <SearchableSelect label="Course / program" required value={subjectCourseId} options={courseOptions} onChange={setSubjectCourseId} placeholder={courseOptions.length ? 'Search courses or programs…' : 'Add a course below first'} emptyMessage="Add a course or program below first." />
                <SearchableSelect label="Choose a specialization (optional)" value={subjectSpecialization} options={specializationOptions} onChange={setSubjectSpecialization} placeholder="Click to view or type the first letters…" />
                {manualSubjectEntry || allowSubjectIdentityEdit ? (
                  <>
                    <label>Subject code<input value={subjectCode} onChange={(event) => setSubjectCode(event.target.value)} placeholder="Official subject code" required maxLength="80" /></label>
                    <label>Subject name<input value={subjectName} onChange={(event) => setSubjectName(event.target.value)} placeholder="Official subject name" required minLength="2" maxLength="160" /></label>
                  </>
                ) : subjectEditId ? (
                  <div className="selected-subject-summary"><strong>{subjectName}</strong><span>Official code: {subjectCode}</span><button type="button" className="text-action" onClick={() => setAllowSubjectIdentityEdit(true)}>Edit subject name or code</button></div>
                ) : null}
                <SearchableSelect label="Term" value={customTerm ? '__add_new__' : subjectTerm} options={[...termOptions.map((term) => ({ value: term, label: term })), { value: '__add_new__', label: '+ Add a new term' }]} onChange={(value) => { if (value === '__add_new__') { setCustomTerm(true); setSubjectTerm('') } else { setCustomTerm(false); setSubjectTerm(value) } }} placeholder="Search terms or add one…" />
                {customTerm && <label>New term<input value={subjectTerm} onChange={(event) => setSubjectTerm(event.target.value)} placeholder="e.g., Fall 2026" required maxLength="40" /></label>}
                <label>Semester<select value={subjectSemester} onChange={(event) => setSubjectSemester(event.target.value)}>{[1, 2, 3, 4, 5, 6].map((semester) => <option key={semester} value={semester}>Semester {semester}</option>)}</select></label>
                <SearchableSelect label="Section" value={customSection ? '__add_new__' : subjectSection} options={[...sectionOptions.map((section) => ({ value: section, label: section })), { value: '__add_new__', label: '+ Add a new section' }]} onChange={(value) => { if (value === '__add_new__') { setCustomSection(true); setSubjectSection('') } else { setCustomSection(false); setSubjectSection(value) } }} placeholder="Search sections or add one…" />
                {customSection && <label>New section<input value={subjectSection} onChange={(event) => setSubjectSection(event.target.value)} placeholder="e.g., A or B" required maxLength="40" /></label>}
                <button className="login-submit" type="submit" disabled={!subjectEditId && !manualSubjectEntry}>{subjectEditId ? 'Save subject' : 'Add subject'}</button>
                {(subjectEditId || manualSubjectEntry) && <button type="button" className="text-action" onClick={() => { setSubjectEditId(null); setManualSubjectEntry(false); setAllowSubjectIdentityEdit(false); setSubjectCode(''); setSubjectName(''); setSubjectSpecialization(''); setSubjectSemester('1'); setSubjectTerm(''); setSubjectSection(''); setCustomTerm(false); setCustomSection(false) }}>Cancel</button>}
              </form>
              <form className="catalog-form" onSubmit={addFacultyAssignment}>
                <h2>Assign faculty to a subject</h2>
                <SearchableSelect label="Faculty member" required value={assignmentFacultyId} options={facultyOptions} onChange={setAssignmentFacultyId} placeholder="Search by name or username…" emptyMessage="No faculty accounts found. Add a faculty account first." />
                <SearchableSelect label="Subject to assign" required value={assignmentSubjectId} options={assignmentSubjectOptions} onChange={setAssignmentSubjectId} placeholder="Type a few letters of the subject name or code…" emptyMessage="Add a subject first." />
                <button className="login-submit" type="submit">Save assignment</button>
              </form>
            </div>
            <section className="specialization-management">
              <div className="catalog-table-heading"><h2>Courses and programs</h2><span>{adminOptions.courses.length} total</span></div>
              <p>Search for an existing course to update it. Add a new one only when the university introduces it.</p>
              {adminOptions.courses.length > 0 && <div className="specialization-browser"><SearchableSelect
                label="Search existing courses"
                value={courseEditId ? String(courseEditId) : ''}
                options={[{ value: '', label: 'Choose a course…' }, ...adminOptions.courses.map((course) => ({ value: String(course.id), label: String(course.name || '').trim().toUpperCase() === String(course.code || '').trim().toUpperCase() ? course.name : `${course.name} · ${course.code}` }))]}
                onChange={(value) => {
                  const selected = adminOptions.courses.find((course) => String(course.id) === value)
                  setCourseEditId(selected?.id ?? null)
                  setCourseName(selected?.name || '')
                  setCourseCode(selected?.code || '')
                  setCourseFormOpen(Boolean(selected))
                }}
                placeholder="Type a few letters of the course name or code…"
                emptyMessage="No matching course."
              /><small>Select a course to edit its name or code.</small></div>}
              {!courseFormOpen && <button type="button" className="catalog-select-button" onClick={() => { setCourseEditId(null); setCourseName(''); setCourseCode(''); setCourseFormOpen(true) }}>＋ Add a new course</button>}
              {courseFormOpen && <form className="catalog-form specialization-form" onSubmit={addCourse}>
                <h3>{courseEditId ? 'Edit selected course' : 'Add a new course'}</h3>
                <label>Course or program name<input value={courseName} onChange={(event) => setCourseName(event.target.value)} placeholder="e.g., Master of Computer Applications" required minLength="2" maxLength="160" /></label>
                <label>Course code<input value={courseCode} onChange={(event) => setCourseCode(event.target.value)} placeholder="e.g., MCA" required minLength="2" maxLength="80" /></label>
                <div className="specialization-form-actions"><button className="login-submit" type="submit" disabled={courseSaving}>{courseSaving ? 'Saving…' : courseEditId ? 'Save course changes' : 'Add course'}</button>{courseEditId && <button type="button" className="text-action destructive-action" disabled={courseSaving} onClick={() => { const course = adminOptions.courses.find((item) => String(item.id) === String(courseEditId)); if (course) removeCourse(course) }}>Remove course</button>}<button type="button" className="text-action" onClick={() => { setCourseFormOpen(false); setCourseEditId(null); setCourseName(''); setCourseCode('') }}>Cancel</button></div>
              </form>}
            </section>
            <section className="specialization-management">
              <div className="catalog-table-heading"><h2>Specializations</h2><span>{specializations.length} total</span></div>
              <p>Search for a specialization to edit it, or add a new one.</p>
              {specializations.length > 0 && <>
              <div className="specialization-browser">
                <SearchableSelect
                  label="Search existing specializations"
                  value={specializationListFilter}
                  options={[{ value: '', label: 'Choose a specialization…' }, ...specializations.map((item) => ({ value: String(item.id), label: item.name }))]}
                  onChange={(value) => {
                    setSpecializationListFilter(value)
                    const selected = specializations.find((item) => String(item.id) === value)
                    setSpecializationEditId(selected?.id ?? null)
                    setSpecializationName(selected?.name || '')
                    setSpecializationFormOpen(Boolean(selected))
                  }}
                  placeholder="Type a few letters of the specialization…"
                  emptyMessage="No matching specialization."
                />
                <small>Select one to edit it without retyping its name.</small>
              </div>
              {(() => {
                const visibleSpecializations = specializationListFilter
                  ? specializations.filter((item) => String(item.id) === specializationListFilter)
                  : specializations
                return visibleSpecializations.length > 0
                  ? <div className="catalog-chip-list">{visibleSpecializations.map((item) => <div className="catalog-chip" key={item.id}><span>{item.name}</span><button type="button" className="text-action" onClick={() => { setSpecializationListFilter(String(item.id)); setSpecializationEditId(item.id); setSpecializationName(item.name); setSpecializationFormOpen(true); document.querySelector('.specialization-form')?.scrollIntoView({ behavior: 'smooth', block: 'center' }) }}>Edit</button><button type="button" className="text-action destructive-action" onClick={() => removeSpecialization(item)}>Remove</button></div>)}</div>
                  : <div className="role-list-message">No specializations match that selection.</div>
              })()}
              </>}
              {!specializationFormOpen && <button type="button" className="catalog-select-button" onClick={() => { setSpecializationEditId(null); setSpecializationName(''); setSpecializationListFilter(''); setSpecializationFormOpen(true) }}>＋ Add a new specialization</button>}
              {specializationFormOpen && <form className="catalog-form specialization-form" onSubmit={saveSpecialization}>
                <h3>{specializationEditId ? 'Edit selected specialization' : 'Add a new specialization'}</h3>
                <label>Specialization name<input value={specializationName} onChange={(event) => setSpecializationName(event.target.value)} placeholder="e.g., Data Science" required minLength="2" maxLength="120" /></label>
                <div className="specialization-form-actions"><button className="login-submit" type="submit">{specializationEditId ? 'Save changes' : 'Add specialization'}</button><button type="button" className="text-action" onClick={() => { setSpecializationFormOpen(false); setSpecializationEditId(null); setSpecializationName(''); setSpecializationListFilter('') }}>Cancel</button></div>
              </form>}
            </section>
            <div className="catalog-table-heading"><h2>Faculty assignments</h2><span>{facultyAssignments.length} total</span></div>
            {facultyAssignments.length === 0 ? <div className="role-list-message">No faculty have been assigned to subjects yet.</div> : <div className="role-table-wrap"><table className="role-table"><thead><tr><th>Faculty</th><th>Subject</th><th>Term</th><th>Actions</th></tr></thead><tbody>{facultyAssignments.map((assignment) => <tr key={assignment.id}><td>{assignment.faculty_name} · {assignment.username}</td><td>{assignment.subject_code} · {assignment.subject_name}</td><td>{assignment.term || `Semester ${assignment.semester}`}</td><td><button type="button" className="text-action destructive-action" onClick={() => removeFacultyAssignment(assignment)}>Remove</button></td></tr>)}</tbody></table></div>}
            <div className="catalog-table-heading"><h2>Student subject enrollment</h2><span>{studentEnrollmentRows.length} enrollments</span></div>
            <p>Enroll students in subjects so they can upload submissions and access subject notes.</p>
            <form className="catalog-form" onSubmit={saveStudentEnrollments}>
              <SearchableSelect label="Student" required value={enrollmentStudentId} options={(adminOptions.students || []).map((student) => ({ value: String(student.id), label: `${student.full_name} · ${student.username}` }))} onChange={setEnrollmentStudentId} placeholder="Search students by name or username…" emptyMessage="Add a student account first." />
              <fieldset className="enrollment-subject-picker"><legend>Subjects</legend>{subjects.map((subject) => <label key={subject.id}><input type="checkbox" checked={enrollmentSubjectIds.includes(String(subject.id))} onChange={(event) => setEnrollmentSubjectIds((ids) => event.target.checked ? [...ids, String(subject.id)] : ids.filter((id) => id !== String(subject.id)))} />{subject.name} · {subject.code}</label>)}</fieldset>
              <button className="login-submit" type="submit" disabled={!adminOptions.students?.length || !subjects.length || !enrollmentSubjectIds.length}>Enroll student in selected subjects</button>
            </form>
            {studentEnrollmentRows.length === 0 ? <div className="role-list-message">No student-subject enrollments yet.</div> : <div className="role-table-wrap"><table className="role-table"><thead><tr><th>Student</th><th>Subject</th><th>Action</th></tr></thead><tbody>{studentEnrollmentRows.map((enrollment) => <tr key={enrollment.id}><td>{enrollment.student_name} · {enrollment.username}</td><td>{enrollment.subject_name} · {enrollment.subject_code}</td><td><button type="button" className="text-action destructive-action" onClick={() => removeStudentEnrollment(enrollment)}>Remove enrollment</button></td></tr>)}</tbody></table></div>}
            <div className="catalog-table-heading"><h2>Current subject catalog</h2><span>{subjects.length} subjects · {specializations.length} specializations</span></div>
            {catalogLoading ? <div className="role-list-message">Loading catalog…</div> : subjects.length === 0 ? <div className="role-list-message">No subjects yet. Add the official subject details above.</div> : (
              <div className="role-table-wrap"><table className="role-table"><thead><tr><th>Term</th><th>Code</th><th>Subject</th><th>Faculty</th><th>Section</th><th>Semester</th><th>Actions</th></tr></thead><tbody>{subjects.map((subject) => {
                const assignedFaculty = facultyAssignments.filter((assignment) => assignment.subject_id === subject.id).map((assignment) => assignment.faculty_name)
                return <tr key={subject.id}><td>{subject.term || '—'}</td><td>{subject.code}</td><td>{subject.name}</td><td>{assignedFaculty.join(', ') || subject.instructor_name || '—'}</td><td>{subject.section || '—'}</td><td>{subject.semester}</td><td><button type="button" className="text-action" onClick={() => beginSubjectEdit(subject)}>Edit</button><button type="button" className="text-action destructive-action" onClick={() => removeSubject(subject)}>Remove</button></td></tr>
              })}</tbody></table></div>
            )}
          </section>
        ) : activePage === 'courses' && user.role === 'student' ? (
          <section className="role-list-page catalog-page">
            <span className="eyebrow">STUDENT SPACE</span><h1>My enrolled subjects</h1><p>These are the MCA subjects Admin has enrolled you in.</p>
            {catalogError && <div className="error-note" role="alert">{catalogError}</div>}
            {catalogLoading ? <div className="role-list-message">Loading your enrolled subjects…</div> : subjects.length === 0 ? <div className="role-list-message">No subjects are linked to your student account yet. Ask Admin to enroll you.</div> : <div className="role-table-wrap"><table className="role-table"><thead><tr><th>Term</th><th>Subject</th><th>Code</th><th>Faculty</th><th>Section</th><th>Semester</th><th>Ask</th></tr></thead><tbody>{subjects.map((subject) => <tr key={subject.id}><td>{subject.term || '—'}</td><td>{subject.name}</td><td>{subject.code}</td><td>{subject.instructor_name || 'Not listed'}</td><td>{subject.section || '—'}</td><td>{subject.semester}</td><td><button className="text-action" onClick={() => askCampusGPT(`Help me with ${subject.name} (${subject.code})`)}>Ask CampusGPT</button></td></tr>)}</tbody></table></div>}
          </section>
        ) : activePage === 'courses' && user.role === 'faculty' ? (
          <section className="role-list-page catalog-page">
            <span className="eyebrow">FACULTY WORKSPACE</span><h1>My assigned subjects</h1><p>These MCA subjects have been assigned to your faculty account by Admin.</p>
            {catalogError && <div className="error-note" role="alert">{catalogError}</div>}
            <div className="catalog-search-row"><input type="search" value={subjectSearch} onChange={(event) => setSubjectSearch(event.target.value)} placeholder="Search by subject name or code…" aria-label="Search subjects"/><select value={specializationFilter} onChange={(event) => setSpecializationFilter(event.target.value)} aria-label="Filter by specialization"><option value="">All specializations</option>{specializations.map((item) => <option key={item.id} value={item.id}>{item.name}</option>)}</select></div>
            {catalogLoading ? <div className="role-list-message">Loading your subjects…</div> : filteredSubjects.length === 0 ? <div className="role-list-message">No subjects are assigned to your account yet. Ask Admin to assign your courses.</div> : <div className="catalog-subject-grid">{filteredSubjects.map((subject) => <article className="catalog-subject-card" key={subject.id}><span className="eyebrow">{subject.term || `Semester ${subject.semester}`}</span><h2>{subject.name}</h2><p>{subject.code} · Semester {subject.semester}{subject.section ? ` · Section ${subject.section}` : ''}</p><p>{subject.specialization_name || 'MCA'} · Assigned to you</p><button type="button" className="catalog-select-button" onClick={() => { setDocumentSubjectId(String(subject.id)); setActivePage('documents'); setNotice('') }}>Upload notes</button></article>)}</div>}
          </section>
        ) : activePage === 'admin-faculty' && user.role === 'admin' ? (
          <section className="role-list-page">
            <span className="eyebrow">ADMINISTRATION</span><h1>Faculty management</h1><p>Create faculty logins, update faculty details, and remove faculty accounts.</p>
            {recordsError && <div className="error-note" role="alert">{recordsError}</div>}
            <form className="catalog-form faculty-create-form" onSubmit={addFaculty}>
              <h2>Add a faculty account</h2>
              <label>Faculty full name<input value={facultyFullName} onChange={(event) => setFacultyFullName(event.target.value)} required minLength="1" maxLength="120" /></label>
              <label>Username<input value={facultyUsername} onChange={(event) => setFacultyUsername(event.target.value)} autoComplete="off" required minLength="3" maxLength="80" /></label>
              <label>Email<input type="email" value={facultyEmail} onChange={(event) => setFacultyEmail(event.target.value)} required maxLength="255" /></label>
              <label>Initial password<span className="password-input-wrap"><input type={showFacultyInitialPassword ? 'text' : 'password'} value={facultyPassword} onChange={(event) => setFacultyPassword(event.target.value)} autoComplete="new-password" required minLength="8" maxLength="128" /><button className="password-visibility" type="button" aria-label={showFacultyInitialPassword ? 'Hide initial password' : 'Show initial password'} aria-pressed={showFacultyInitialPassword} onClick={() => setShowFacultyInitialPassword((visible) => !visible)}><svg aria-hidden="true" viewBox="0 0 24 24" fill="none"><path d="M2.5 12s3.4-6 9.5-6 9.5 6 9.5 6-3.4 6-9.5 6-9.5-6-9.5-6Z" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round"/><circle cx="12" cy="12" r="2.7" stroke="currentColor" strokeWidth="1.7"/>{!showFacultyInitialPassword && <path d="m4 4 16 16" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round"/>}</svg></button></span></label>
              <small>Share the initial password with the faculty member through a secure channel. The app stores only its password hash.</small>
              <button className="login-submit" type="submit" disabled={facultySaving}>{facultySaving ? 'Saving…' : 'Add faculty'}</button>
            </form>
            <div className="catalog-table-heading"><h2>Faculty accounts</h2><span>{roleRecords.length} faculty</span></div>
            {recordsLoading ? <div className="role-list-message">Loading faculty…</div> : roleRecords.length === 0 ? <div className="role-list-message">No faculty accounts yet. Add the first faculty account above.</div> : <div className="role-table-wrap"><table className="role-table"><thead><tr><th>Full name</th><th>Username</th><th>Email</th><th>Actions</th></tr></thead><tbody>{roleRecords.map((faculty) => facultyEditId === faculty.id ? <tr key={faculty.id}><td><input aria-label="Faculty full name" value={facultyEditValues.full_name} onChange={(event) => setFacultyEditValues((value) => ({ ...value, full_name: event.target.value }))} /></td><td><input aria-label="Faculty username" value={facultyEditValues.username} onChange={(event) => setFacultyEditValues((value) => ({ ...value, username: event.target.value }))} /></td><td><input aria-label="Faculty email" type="email" value={facultyEditValues.email} onChange={(event) => setFacultyEditValues((value) => ({ ...value, email: event.target.value }))} /></td><td><form className="faculty-edit-actions" onSubmit={saveFacultyEdit}><button type="submit" className="text-action">Save</button><button type="button" className="text-action" onClick={() => setFacultyEditId(null)}>Cancel</button></form></td></tr> : <tr key={faculty.id}><td>{faculty.full_name}</td><td>{faculty.username}</td><td>{faculty.email}</td><td><button type="button" className="text-action" onClick={() => beginFacultyEdit(faculty)}>Edit</button><button type="button" className="text-action destructive-action" onClick={() => removeFaculty(faculty)}>Remove</button></td></tr>)}</tbody></table></div>}
            <div className="catalog-table-heading"><h2>Instructors listed in your course screenshots</h2><span>{courseInstructors.length} names</span></div>
            {courseInstructors.length === 0 ? <div className="role-list-message">No instructor names are attached to catalog courses yet.</div> : <div className="role-table-wrap"><table className="role-table"><thead><tr><th>Instructor</th><th>Subjects</th><th>CampusGPT login</th><th>Action</th></tr></thead><tbody>{courseInstructors.map((instructor) => <tr key={instructor.full_name}><td>{instructor.full_name}</td><td>{(instructor.subjects || []).join(', ')}</td><td>{instructor.has_login ? 'Account exists' : 'No login yet'}</td><td>{!instructor.has_login && <button type="button" className="text-action" onClick={() => { setFacultyFullName(instructor.full_name); document.querySelector('.faculty-create-form')?.scrollIntoView({ behavior: 'smooth', block: 'center' }) }}>Set up login</button>}</td></tr>)}</tbody></table></div>}
            <small className="faculty-source-note">Instructor names came from the screenshots. They are not user accounts until an admin supplies a username, email, and initial password.</small>
          </section>
        ) : activePage === 'admin-users' || activePage === 'faculty-students' ? (
          <section className="role-list-page">
            <span className="eyebrow">{user.role === 'admin' ? 'ADMINISTRATION' : 'FACULTY WORKSPACE'}</span>
            <h1>{activePage === 'admin-users' ? 'Student management' : 'Student roster'}</h1>
            <p>{activePage === 'admin-users' ? 'Create student accounts, update their contact details, or remove accounts.' : 'Student accounts available to your faculty account.'}</p>
            {recordsError && <div className="error-note" role="alert">{recordsError}</div>}
            {notice && activePage === 'admin-users' && <div className="success-note" role="status">{notice}</div>}
            {activePage === 'admin-users' ? <>
              <form className="catalog-form faculty-create-form" onSubmit={addStudent}>
                <h2>Add a student account</h2>
                <label>Student full name<input value={studentFullName} onChange={(event) => setStudentFullName(event.target.value)} required minLength="1" maxLength="120" /></label>
                <label>Username<input value={studentUsername} onChange={(event) => setStudentUsername(event.target.value)} autoComplete="off" required minLength="3" maxLength="80" /></label>
                <label>Email<input type="email" value={studentEmail} onChange={(event) => setStudentEmail(event.target.value)} required maxLength="255" /></label>
                <label>Initial password<span className="password-input-wrap"><input type={showStudentInitialPassword ? 'text' : 'password'} value={studentPassword} onChange={(event) => setStudentPassword(event.target.value)} autoComplete="new-password" required minLength="8" maxLength="128" /><button className="password-visibility" type="button" aria-label={showStudentInitialPassword ? 'Hide initial password' : 'Show initial password'} aria-pressed={showStudentInitialPassword} onClick={() => setShowStudentInitialPassword((visible) => !visible)}><svg aria-hidden="true" viewBox="0 0 24 24" fill="none"><path d="M2.5 12s3.4-6 9.5-6 9.5 6 9.5 6-3.4 6-9.5 6-9.5-6-9.5-6Z" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round"/><circle cx="12" cy="12" r="2.7" stroke="currentColor" strokeWidth="1.7"/>{!showStudentInitialPassword && <path d="m4 4 16 16" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round"/>}</svg></button></span></label>
                <small>Give the initial password to the student privately. CampusGPT saves the password as a secure hash.</small>
                <button className="login-submit" type="submit" disabled={recordsLoading}>{recordsLoading ? 'Saving…' : 'Add student'}</button>
              </form>
              <div className="catalog-table-heading"><h2>Student accounts</h2><span>{roleRecordsTotal} students · showing {roleRecords.length}</span></div>
              <div className="catalog-search-row"><input type="search" value={studentSearch} onChange={(event) => { setStudentSearch(event.target.value); setStudentOffset(0); setSelectedStudentIds([]) }} placeholder="Search students by name, username, or email…" aria-label="Search students" /></div>
              {selectedStudentIds.length > 0 && <div className="bulk-action-bar"><span>{selectedStudentIds.length} selected</span><button type="button" className="text-action destructive-action" onClick={removeSelectedStudents}>Remove selected</button></div>}
              {recordsLoading ? <div className="role-list-message">Loading students…</div> : roleRecords.length === 0 ? <div className="role-list-message">No student accounts match. Add a student above or change your search.</div> : <div className="role-table-wrap"><table className="role-table"><thead><tr><th><input type="checkbox" aria-label="Select all students on this page" checked={roleRecords.length > 0 && roleRecords.every((student) => selectedStudentIds.includes(student.id))} onChange={(event) => setSelectedStudentIds(event.target.checked ? roleRecords.map((student) => student.id) : [])} /></th><th>Full name</th><th>Username</th><th>Email</th><th>Actions</th></tr></thead><tbody>{roleRecords.map((student) => studentEditId === student.id ? <tr key={student.id}><td></td><td><input aria-label="Student full name" value={studentEditValues.full_name} onChange={(event) => setStudentEditValues((value) => ({ ...value, full_name: event.target.value }))} /></td><td><input aria-label="Student username" value={studentEditValues.username} onChange={(event) => setStudentEditValues((value) => ({ ...value, username: event.target.value }))} /></td><td><input aria-label="Student email" type="email" value={studentEditValues.email} onChange={(event) => setStudentEditValues((value) => ({ ...value, email: event.target.value }))} /></td><td><form className="faculty-edit-actions" onSubmit={saveStudentEdit}><button type="submit" className="text-action">Save</button><button type="button" className="text-action" onClick={() => setStudentEditId(null)}>Cancel</button></form></td></tr> : <tr key={student.id}><td><input type="checkbox" aria-label={`Select ${student.full_name}`} checked={selectedStudentIds.includes(student.id)} onChange={(event) => setSelectedStudentIds((ids) => event.target.checked ? [...ids, student.id] : ids.filter((id) => id !== student.id))} /></td><td>{student.full_name}</td><td>{student.username}</td><td>{student.email}</td><td><button type="button" className="text-action" onClick={() => beginStudentEdit(student)}>Edit</button><button type="button" className="text-action destructive-action" onClick={() => removeStudent(student)}>Remove</button></td></tr>)}</tbody></table></div>}
              <div className="pagination-controls"><button type="button" className="text-action" disabled={studentOffset === 0 || recordsLoading} onClick={() => setStudentOffset((offset) => Math.max(0, offset - 25))}>← Previous</button><span>{roleRecordsTotal === 0 ? 0 : studentOffset + 1}–{Math.min(studentOffset + roleRecords.length, roleRecordsTotal)} of {roleRecordsTotal}</span><button type="button" className="text-action" disabled={studentOffset + 25 >= roleRecordsTotal || recordsLoading} onClick={() => setStudentOffset((offset) => offset + 25)}>Next →</button></div>
            </> : recordsLoading ? <div className="role-list-message">Loading students…</div> : roleRecords.length === 0 ? <div className="role-list-message">{activePage === 'faculty-students' ? 'No students are enrolled in your assigned subjects yet. Ask Admin to enroll them.' : 'No student accounts found.'}</div> : <div className="role-table-wrap"><table className="role-table"><thead><tr><th>Name</th><th>Username</th></tr></thead><tbody>{roleRecords.map((record) => <tr key={record.id}><td>{record.full_name}</td><td>{record.username}</td></tr>)}</tbody></table></div>}
            <button className="back-button" onClick={() => { setActivePage('dashboard'); setNotice('') }}>← Back to {user.role === 'admin' ? 'Admin' : 'Faculty'} Home</button>
          </section>
        ) : activePage === 'exams' && user.role === 'student' ? (
          <section className="role-list-page">
            <span className="eyebrow">STUDENT SPACE</span><h1>Exam schedule</h1>
            <p>Upcoming exam dates shared by the administration.</p>
            <div className="success-note" role="note">These Semester 3 dates are demo entries for project testing, not an official university timetable.</div>
            {eventsError && <div className="error-note" role="alert">{eventsError}</div>}
            {eventsLoading ? <div className="role-list-message">Loading exam dates…</div> : examEvents.length === 0 ? <div className="role-list-message">No exam dates have been added yet.</div> : <div className="campus-event-list">{examEvents.map((item) => { const badge = eventDateBadge(item.start_at); return <article className="campus-event-card" key={item.id}><span className="event-date exam-date"><small>{badge.month}</small><strong>{badge.day}</strong></span><div className="campus-event-details"><span className="role-badge">Exam</span><h2>{item.title}</h2><p>{eventDateTime(item.start_at)}{item.end_at ? ` – ${eventDateTime(item.end_at)}` : ''}{item.location ? ` · ${item.location}` : ''}</p>{item.description && <p className="campus-event-description">{item.description}</p>}</div></article> })}</div>}
            <button className="back-button" onClick={() => { setActivePage('dashboard'); setNotice('') }}>← Back to Student Home</button>
          </section>
        ) : activePage === 'calendar' ? (
          <section className="role-list-page calendar-page">
            <span className="eyebrow">{user.role === 'admin' ? 'ADMINISTRATION' : `${roleLabel.toUpperCase()} SPACE`}</span>
            <h1>Campus Calendar</h1>
            <p>{user.role === 'admin' ? 'Add and manage campus-wide events. Students and faculty can view the calendar.' : 'Campus-wide events shared by the administration.'}</p>
            {eventsError && <div className="error-note" role="alert">{eventsError}</div>}
            {eventsNotice && <div className="success-note" role="status">{eventsNotice}</div>}
            <section className="month-calendar" aria-label="Campus calendar for 2026 and 2027">
              <div className="month-calendar-toolbar">
                <div className="month-calendar-navigation">
                  <button type="button" aria-label="Previous month" disabled={calendarYear === 2026 && calendarMonthIndex === 0} onClick={() => changeCalendarMonth(-1)}>‹</button>
                  <h2>{new Intl.DateTimeFormat('en-US', { month: 'long' }).format(calendarMonth)}</h2>
                  <button type="button" aria-label="Next month" disabled={calendarYear === 2027 && calendarMonthIndex === 11} onClick={() => changeCalendarMonth(1)}>›</button>
                </div>
                <label className="calendar-year-picker">Year<select value={calendarYear} onChange={(event) => changeCalendarYear(event.target.value)}><option value="2026">2026</option><option value="2027">2027</option></select></label>
              </div>
              <div className="month-calendar-grid" role="grid" aria-label={`${new Intl.DateTimeFormat('en-US', { month: 'long' }).format(calendarMonth)} ${calendarYear}`}>
                {['Sun', 'Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat'].map((weekday) => <span className="calendar-weekday" role="columnheader" key={weekday}>{weekday}</span>)}
                {calendarCells.map((cell, index) => cell ? <button type="button" role="gridcell" key={cell.dateKey} aria-label={`${cell.dateKey}${cell.events.length ? `, ${cell.events.length} campus event${cell.events.length === 1 ? '' : 's'}` : ''}`} aria-pressed={selectedCalendarDate === cell.dateKey} className={`calendar-day${selectedCalendarDate === cell.dateKey ? ' selected' : ''}${cell.dateKey === campusDateKey(new Date()) ? ' today' : ''}${cell.events.length ? ' has-events' : ''}`} onClick={() => setSelectedCalendarDate(cell.dateKey)}><span>{cell.day}</span>{cell.events.length > 0 && <i aria-hidden="true" title={cell.events.map((item) => item.title).join(', ')}>{cell.events.length > 1 ? cell.events.length : '•'}</i>}</button> : <span className="calendar-day empty" key={`empty-${index}`} aria-hidden="true" />)}
              </div>
              <div className="selected-date-events"><h3>{selectedCalendarLabel}</h3>{selectedCalendarEvents.length === 0 ? <p>No campus events on this date.</p> : <ul>{selectedCalendarEvents.map((item) => <li key={item.id}><strong>{item.title}</strong><span>{eventDateTime(item.start_at)}{item.location ? ` · ${item.location}` : ''}</span></li>)}</ul>}</div>
            </section>
            {user.role === 'admin' && <form className="catalog-form campus-event-form" onSubmit={saveCampusEvent}>
              <h2>{eventEditId ? 'Edit campus event' : 'Add a campus event'}</h2>
              <label>Event name<input value={eventForm.title} onChange={(event) => setEventForm((form) => ({ ...form, title: event.target.value }))} placeholder="e.g., MCA project showcase" required minLength="2" maxLength="160" /></label>
              <label>Event type<select value={eventForm.event_type} onChange={(event) => setEventForm((form) => ({ ...form, event_type: event.target.value }))}><option value="campus">Campus event</option><option value="academic">Academic</option><option value="exam">Exam</option><option value="deadline">Deadline</option></select></label>
              <label>Start date and time<input type="datetime-local" value={eventForm.start_at} onChange={(event) => setEventForm((form) => ({ ...form, start_at: event.target.value }))} required /></label>
              <label>End date and time (optional)<input type="datetime-local" value={eventForm.end_at} onChange={(event) => setEventForm((form) => ({ ...form, end_at: event.target.value }))} /></label>
              <label>Location (optional)<input value={eventForm.location} onChange={(event) => setEventForm((form) => ({ ...form, location: event.target.value }))} placeholder="e.g., Seminar Hall" maxLength="200" /></label>
              <label>Details (optional)<textarea value={eventForm.description} onChange={(event) => setEventForm((form) => ({ ...form, description: event.target.value }))} placeholder="Share useful details about this event." rows="3" maxLength="4000" /></label>
              <button className="login-submit" type="submit" disabled={eventSaving}>{eventSaving ? 'Saving…' : eventEditId ? 'Save event' : 'Add event'}</button>
              {eventEditId && <button className="text-action" type="button" onClick={() => { setEventEditId(null); setEventForm(emptyEventForm) }}>Cancel edit</button>}
            </form>}
            <div className="catalog-table-heading"><h2>Campus events</h2><span>{campusEvents.length} listed</span></div>
            {eventsLoading ? <div className="role-list-message">Loading campus events…</div> : campusEvents.length === 0 ? <div className="role-list-message">No events have been added yet.</div> : <div className="campus-event-list">{campusEvents.map((item) => { const badge = eventDateBadge(item.start_at); return <article className="campus-event-card" key={item.id}><span className={`event-date ${item.event_type === 'exam' ? 'exam-date' : 'assignment-date'}`}><small>{badge.month}</small><strong>{badge.day}</strong></span><div className="campus-event-details"><span className="role-badge">{item.event_type}</span><h2>{item.title}</h2><p>{eventDateTime(item.start_at)}{item.end_at ? ` – ${eventDateTime(item.end_at)}` : ''}{item.location ? ` · ${item.location}` : ''}</p>{item.description && <p className="campus-event-description">{item.description}</p>}</div>{user.role === 'admin' && <div className="campus-event-actions"><button type="button" className="text-action" onClick={() => beginCampusEventEdit(item)}>Edit</button><button type="button" className="text-action destructive-action" onClick={() => removeCampusEvent(item)}>Remove</button></div>}</article> })}</div>}
          </section>
        ) : activePage === 'attendance' && user.role === 'faculty' ? (
          <section className="role-list-page attendance-page">
            <span className="eyebrow">FACULTY WORKSPACE</span><h1>Record attendance</h1><p>Choose one of your assigned subjects and date, then mark enrolled students present or absent.</p>
            {recordsError && <div className="error-note" role="alert">{recordsError}</div>}
            {attendanceMessage && <div className="success-note" role="status">{attendanceMessage}</div>}
            {attendanceError && <div className="error-note" role="alert">{attendanceError}</div>}
            {recordsLoading ? <div className="role-list-message">Loading enrolled students…</div> : roleRecords.length === 0 ? <div className="role-list-message">No students are enrolled in your assigned subjects yet. Ask Admin to enroll them.</div> : (
              <form onSubmit={saveAttendance}>
                <div className="attendance-fields"><SearchableSelect label="Subject" required value={attendanceCourse} options={subjects.map((subject) => ({ value: String(subject.id), label: `${subject.name} · ${subject.code}` }))} onChange={setAttendanceCourse} placeholder="Search your assigned subjects…" emptyMessage="No subjects are assigned to your account." /><label>Class date<input type="date" value={attendanceDate} onChange={(event) => setAttendanceDate(event.target.value)} required /></label></div>
                <div className="role-table-wrap"><table className="role-table attendance-table"><thead><tr><th>Student</th><th>Username</th><th>Attendance</th></tr></thead><tbody>{roleRecords.map((student) => <tr key={student.id}><td>{student.full_name}</td><td>{student.username}</td><td><select aria-label={`Attendance for ${student.full_name}`} value={attendanceMarks[student.id] || 'present'} onChange={(event) => setAttendanceMarks((items) => ({ ...items, [student.id]: event.target.value }))}><option value="present">Present</option><option value="absent">Absent</option></select></td></tr>)}</tbody></table></div>
                <button className="login-submit attendance-submit" type="submit" disabled={attendanceSaving || recordsLoading || roleRecords.length === 0 || !attendanceCourse}>{attendanceSaving ? 'Saving attendance…' : 'Save attendance'}</button>
              </form>
            )}
            <div className="catalog-table-heading"><h2>Attendance history</h2><span>{attendanceHistory.length} classes</span></div>
            {attendanceHistoryError && <div className="error-note" role="alert">{attendanceHistoryError}</div>}
            {attendanceHistoryLoading ? <div className="role-list-message">Loading attendance history…</div> : attendanceHistory.length === 0 ? <div className="role-list-message">No attendance has been recorded yet.</div> : <div className="role-table-wrap"><table className="role-table"><thead><tr><th>Subject</th><th>Date</th><th>Present</th><th>Absent</th><th>Students recorded</th></tr></thead><tbody>{attendanceHistory.map((session, index) => <tr key={`${session.subject_id || session.subject_name}-${session.session_date}-${index}`}><td>{session.subject_name}</td><td>{new Date(`${session.session_date}T00:00:00`).toLocaleDateString()}</td><td>{session.present_count}</td><td>{session.absent_count}</td><td>{session.students_recorded}{session.sessions_recorded > 1 ? ` · ${session.sessions_recorded} earlier records` : ''}</td></tr>)}</tbody></table></div>}
            <button className="back-button" onClick={() => { setActivePage('dashboard'); setNotice('') }}>← Back to Faculty Home</button>
          </section>
        ) : activePage === 'attendance' && user.role === 'student' ? (
          <section className="role-list-page attendance-page">
            <span className="eyebrow">STUDENT SPACE</span><h1>My attendance</h1><p>Your attendance records saved by faculty.</p>
            {attendanceError && <div className="error-note" role="alert">{attendanceError}</div>}
            {attendanceLoading ? <div className="role-list-message">Loading your attendance…</div> : (
              <>
                <div className="attendance-summary"><article><span>ATTENDANCE</span><strong>{attendanceSummary.percentage}%</strong></article><article><span>PRESENT</span><strong>{attendanceSummary.present}</strong></article><article><span>CLASSES RECORDED</span><strong>{attendanceSummary.total}</strong></article></div>
                {attendanceSummary.records.length === 0 ? <div className="role-list-message">No attendance has been recorded for your account yet.</div> : <div className="role-table-wrap"><table className="role-table"><thead><tr><th>Course</th><th>Date</th><th>Status</th></tr></thead><tbody>{attendanceSummary.records.map((record) => <tr key={record.session_id}><td>{record.course_name}</td><td>{record.session_date}</td><td><span className={`role-badge attendance-${record.status}`}>{record.status}</span></td></tr>)}</tbody></table></div>}
              </>
            )}
            <button className="back-button" onClick={() => { setActivePage('dashboard'); setNotice('') }}>← Back to Student Home</button>
          </section>
        ) : activePage === 'history' && user.role === 'student' ? (
          <section className="role-list-page chat-history-page">
            <div className="chat-history-heading"><div><span className="eyebrow">STUDENT SPACE</span><h1>Chat History</h1><p>Saved conversations are private to your student account.</p></div><div className="chat-history-heading-actions"><button type="button" className="back-button" onClick={startNewChat}>＋ New chat</button><button type="button" className="text-action destructive-action" disabled={!chatHistory.length || clearingChatHistory} onClick={clearStudentChatHistory}>{clearingChatHistory ? 'Deleting…' : 'Delete all'}</button></div></div>
            {chatHistoryError && <div className="error-note" role="alert">{chatHistoryError}</div>}
            {chatHistoryLoading ? <div className="role-list-message">Loading your saved conversations…</div> : chatHistory.length === 0 ? <div className="role-list-message">No saved conversations yet. Start a chat with CampusGPT and it will appear here.</div> : <div className="chat-history-list">{chatHistory.map((item) => <article className="chat-history-card" key={item.id}><div className="chat-history-card-copy"><h2>{item.title}</h2><p>{new Intl.DateTimeFormat('en-IN', { dateStyle: 'medium', timeStyle: 'short' }).format(new Date(item.updated_at))} · {item.message_count} {item.message_count === 1 ? 'question' : 'questions'}</p></div><div className="chat-history-card-actions"><button type="button" className="catalog-select-button" disabled={openingChatId === item.id} onClick={() => openStudentChat(item.id)}>{openingChatId === item.id ? 'Opening…' : 'Open chat'}</button><button type="button" className="text-action destructive-action" disabled={deletingChatId === item.id} onClick={() => deleteStudentConversation(item.id, item.title)}>{deletingChatId === item.id ? 'Deleting…' : 'Delete'}</button></div></article>)}</div>}
          </section>
        ) : isChat ? (
          <section className="chat-page"><div className="chat-heading"><span className="eyebrow"><span className="online-dot"/> YOUR ACADEMIC ASSISTANT</span><h1>Ask CampusGPT<span>.</span></h1><p>{user.role === 'admin' ? 'Ask about live faculty, subject catalog, and campus calendar records, or shared campus documents.' : 'Get clear, friendly answers grounded in your MCA course and campus documents.'}</p></div>
            {user.role === 'student' && <div className="chat-history-toolbar"><button type="button" className="text-action" onClick={() => { setActivePage('history'); setNotice('') }}>← Chat History</button><div><button type="button" className="text-action" disabled={loading} onClick={startNewChat}>＋ New chat</button>{activeChatId !== null && <button type="button" className="text-action destructive-action" disabled={loading || deletingChatId === activeChatId} onClick={() => deleteStudentConversation(activeChatId, conversation[0]?.question || 'this chat')}>Delete chat</button>}</div></div>}
            {conversation.length === 0 ? <div className="welcome-card"><div className="welcome-icon">✳</div><h2>What do you want to know?</h2><p>Ask naturally about courses, exams, fees, schedules, or campus life.</p><div className="suggestion-list">{suggestions.map((item) => <button key={item} onClick={() => askCampusGPT(item)}>{item}<span>↗</span></button>)}</div></div> : <div className="conversation">{conversation.map((item, index) => <article className="exchange" key={`${item.question}-${index}`}><div className="user-question"><span className="avatar small">{initial}</span><p>{item.question}</p></div><div className="ai-answer"><div className="answer-mark">✳</div><div className="answer-body"><strong>CampusGPT</strong>{item.answer ? <p>{normalizeCampusGPTAnswer(item.answer).replace(/\s*\[\d+\]/g, '')}</p> : <p className="thinking">Looking through your campus resources…</p>}</div></div></article>)}</div>}
            {error && <div className="error-note" role="alert">{error}</div>}
            <form className="composer" onSubmit={(event) => { event.preventDefault(); askCampusGPT() }}><textarea value={question} onChange={(event) => setQuestion(event.target.value)} onKeyDown={(event) => { if (event.key === 'Enter' && !event.shiftKey) { event.preventDefault(); askCampusGPT() } }} placeholder="Message CampusGPT…" rows="1" aria-label="Your question"/><button className="send-button" disabled={loading || !question.trim()} aria-label="Send question">{loading ? '…' : '↑'}</button><div className="composer-foot"><span>CampusGPT can make mistakes. Check the source when details matter.</span><span>Enter to send · Shift+Enter for a new line</span></div></form>
          </section>
        ) : (
          <section className="preview-page"><span className="eyebrow">{roleLabel.toUpperCase()} SPACE</span><h1>{currentLabel}</h1><p>{notice || 'This section is part of the dashboard preview.'}</p><button className="back-button" onClick={() => { setActivePage('dashboard'); setNotice('') }}>← Back to Dashboard</button></section>
        )}
      </main>
    </div>
  )
}

export default App
