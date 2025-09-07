# Copyright © 2025 Preetimant Bora Bhowal. All rights reserved.
# Unauthorized copying, distribution, or use of this file is strictly prohibited.
from flask import Flask, request, jsonify
from flask_cors import CORS
from owlready2 import get_ontology
from functools import lru_cache
import logging
import re
import json

app = Flask(__name__)
CORS(app)
logging.basicConfig(level=logging.INFO)

# =====================
# Configuration
# =====================
ONTOLOGY_PATH = "university_courses.owl"
ERROR_TEMPLATES = {
    "invalid_input": "Please provide a valid {entity} (3-50 characters).",
    "not_found": "I couldn't find {entity} '{name}'.",
    "no_data": "No {data_type} available for {entity} '{name}'.",
    "pagination": "\n\n(Page {current}/{total} - Say 'next page' or 'previous page')"
}
PAGE_SIZE = 3
MAX_INPUT_LENGTH = 50

# Load ontology
onto = get_ontology(ONTOLOGY_PATH).load()

# =====================
# Helper Functions
# =====================
def sanitize_id(name: str) -> str:
    """Convert names to valid ontology IDs."""
    return re.sub(r'\W+', '_', name.strip().lower())

def validate_input(value: str) -> bool:
    """Validate user-provided parameters."""
    if not value or len(value) > MAX_INPUT_LENGTH:
        return False
    return bool(re.match(r"^[\w\s-]+$", value))

def get_nested_property(obj, property_path: str):
    """
    Safely navigate nested ontology properties given a dot-separated property path.
    Returns the first non-"NA" value or None.
    """
    try:
        properties = property_path.split('.')
        for prop in properties:
            if isinstance(obj, list):
                if not obj:
                    return None
                obj = obj[0]
            if not hasattr(obj, prop):
                return None
            obj = getattr(obj, prop)
        if isinstance(obj, list):
            return obj[0] if obj else None
        return obj if obj not in [None, "NA"] else None
    except Exception as e:
        logging.error(f"Error in get_nested_property: {e}")
        return None

def paginate_items(items, page_size=PAGE_SIZE):
    """Split a list of items into pages."""
    return [items[i:i+page_size] for i in range(0, len(items), page_size)]

# =====================
# Cached Data Access
# =====================
@lru_cache(maxsize=100)
def get_course(course_name: str):
    """Return the course individual from the ontology."""
    if not validate_input(course_name):
        logging.warning(f"Invalid course input: {course_name}")
        return None
    course_id = sanitize_id(course_name)
    return next(iter(onto.search(iri=f"*#{course_id}")), None)

@lru_cache(maxsize=50)
def get_instructor(instructor_name: str):
    """Return the instructor individual from the ontology."""
    if not validate_input(instructor_name):
        logging.warning(f"Invalid instructor input: {instructor_name}")
        return None
    return next(iter(onto.search(Instructors=instructor_name.strip())), None)

def get_course_metadata(course):
    """Return the CourseMetadata individual for a course."""
    try:
        return course.hasCourseMetadata[0]
    except (AttributeError, IndexError):
        return None

def get_basic_info(course):
    """Return the BasicInfo individual for a course."""
    try:
        return course.hasBasicInfo[0]
    except (AttributeError, IndexError):
        return None

# =====================
# Query Handlers for Each Query
# =====================

# 1 & 6. Who teaches {course}? / {course} is taught by whom?
def query_instructor_for_course(params):
    course = get_course(params.get("courseName", ""))
    if course:
        instructors = [ins.Instructors for ins in course.hasInstructorDetails if ins.Instructors]
        if instructors:
            return f"{', '.join(instructors)} teaches {params.get('courseName')}."
        return "No instructor listed."
    return ERROR_TEMPLATES["not_found"].format(entity="course", name=params.get("courseName"))

# 2. In which programs is {course} taught/conducted?
def query_program_for_course(params):
    course = get_course(params.get("courseName", ""))
    if course and course.belongsToTerm:
        term = course.belongsToTerm[0]
        if term and term.belongsToProgram:
            program = term.belongsToProgram[0]
            return f"Taught in {program.programName} program."
    return "Program not found."

# 3. Which {term} is {course} conducted for {program}?
def query_term_for_course_program(params):
    course = get_course(params.get("courseName", ""))
    program_param = sanitize_id(params.get("program", ""))
    if course:
        # Iterate over all Term individuals in the ontology and check for the course and program match
        for term in onto.search(type=onto.Term):
            if term in course.belongsToTerm and term.belongsToProgram and program_param in term.belongsToProgram[0].name:
                return f"Term {term.name.split('_')[-1]}"
    return "Course not found in program."

# 4. What are the assessment tools used in {course}?
def query_assessment_tools(params):
    course = get_course(params.get("courseName", ""))
    if course:
        tools = [a.AssessmentTool for a in course.hasAssessment if a.AssessmentTool]
        if tools:
            return f"Assessment tools: {', '.join(tools)}."
        return "No assessments listed."
    return ERROR_TEMPLATES["not_found"].format(entity="course", name=params.get("courseName"))

# 5 & 14. What is the percentage of the {assessment tool} in {course}? / What percentage does {assessment tool} contribute?
def query_assessment_percentage(params):
    course = get_course(params.get("courseName", ""))
    tool_name = params.get("assessmentTool", "")
    if course and course.hasAssessment:
        for assessment in course.hasAssessment:
            if assessment.AssessmentTool and assessment.AssessmentTool.lower() == tool_name.lower():
                if assessment.Percentage:
                    return f"{assessment.Percentage}%"
                else:
                    return ERROR_TEMPLATES["no_data"].format(
                        data_type="assessment percentage",
                        entity="course",
                        name=params.get("courseName")
                    )
        return ERROR_TEMPLATES["not_found"].format(entity="assessment tool", name=tool_name)
    return ERROR_TEMPLATES["not_found"].format(entity="course", name=params.get("courseName"))

# 7. How many credits is {course} worth?
def query_course_credits(params):
    course = get_course(params.get("courseName", ""))
    meta = get_course_metadata(course)
    if meta and meta.CourseCredit:
        return f"{meta.CourseCredit} credits."
    return "Credit info unavailable."

# 8. Session {session number} info of {course}?
def query_session_info(params):
    course = get_course(params.get("courseName", ""))
    session_num = str(params.get("sessionNumber", ""))
    if course:
        session = next((s for s in course.hasSessionPlan if str(s.Session) == session_num), None)
        if session:
            details = f"Module: {session.Module}, Topic: {session.Topic}, Materials: {session.ReadingMaterial}"
            return details.replace("NA, ", "").replace("NA", "")
    return "Session information not found."

# 9. What reading materials are required for {course}?
def query_reading_materials(params):
    course = get_course(params.get("courseName", ""))
    if course:
        materials = [s.ReadingMaterial for s in course.hasSessionPlan if s.ReadingMaterial and s.ReadingMaterial != "NA"]
        if materials:
            return "Required readings:\n" + "\n".join(materials[:5])
        return "No reading materials listed."
    return ERROR_TEMPLATES["not_found"].format(entity="course", name=params.get("courseName"))

# 10. Contact detail of {instructor} of {course}?
def query_instructor_contact(params):
    course = get_course(params.get("courseName", ""))
    if course and course.hasInstructorDetails:
        instructor = course.hasInstructorDetails[0]
        details = f"Contact: {instructor.ContactDetails}, Office: {instructor.Office}, Hours: {instructor.ConsultationHours}"
        return details.replace("NA, ", "").replace("NA", "")
    return "Instructor contact not found."

# 11. How do I contact {instructor}?
def query_contact_instructor(params):
    instructor_name = params.get("instructorName", "")
    inst = get_instructor(instructor_name)
    if inst and inst.ContactDetails:
        return f"Contact: {inst.ContactDetails}, Consultation Hours: {inst.ConsultationHours}"
    return ERROR_TEMPLATES["not_found"].format(entity="instructor", name=instructor_name)

# 12. What course is taught by {instructor}?
def query_courses_by_instructor(params):
    instructor_name = params.get("instructorName", "")
    inst = get_instructor(instructor_name)
    if inst and hasattr(inst, "teachesCourse"):
        courses = inst.teachesCourse
        if courses:
            course_titles = []
            for course in courses:
                meta = get_course_metadata(course)
                if meta and meta.CourseCodeTitle:
                    course_titles.append(meta.CourseCodeTitle)
            if course_titles:
                return f"{instructor_name} teaches: {', '.join(course_titles)}."
        return ERROR_TEMPLATES["no_data"].format(data_type="courses", entity="instructor", name=instructor_name)
    return ERROR_TEMPLATES["not_found"].format(entity="instructor", name=instructor_name)

# 13. How many sessions does {course} have?
def query_total_sessions(params):
    course = get_course(params.get("courseName", ""))
    meta = get_course_metadata(course)
    if meta and meta.TotalSessions:
        return f"{meta.TotalSessions} sessions."
    return "Total sessions info unavailable."

# 15. What are the prerequisites for {course}?
def query_prerequisites(params):
    return handle_standard_query(params, "hasCourseMetadata.Prerequisites", "prerequisites")

# 16. Which batch or year is {course} offered to?
def query_year_batch(params):
    return handle_standard_query(params, "hasCourseMetadata.YearBatch", "year/batch")

# 17. What sections is {course} offered for?
def query_sections(params):
    return handle_standard_query(params, "hasCourseMetadata.Sections", "sections")

# 18. What is {course}? (Course overview from BasicInfo)
def query_course_overview(params):
    return handle_standard_query(params, "hasBasicInfo.Introduction", "course overview")

# 19. What are the learning outcomes for {course}?
def query_learning_outcomes(params):
    return handle_standard_query(params, "hasBasicInfo.LearningOutcomes", "learning outcomes")

# 20. What is the pedagogy used in {course}?
def query_pedagogy(params):
    return handle_standard_query(params, "hasBasicInfo.PedagogyUsed", "pedagogy information")

# 21. How long is each session for {course}?
def query_session_duration(params):
    return handle_standard_query(params, "hasCourseMetadata.SessionDuration", "session duration")

# 22. How many assessment tools are used in {course} and what are their details?
def query_assessment_details_full(params):
    course = get_course(params.get("courseName", ""))
    if course and course.hasAssessment:
        details = []
        for a in course.hasAssessment:
            tool = a.AssessmentTool if a.AssessmentTool else "Unknown Tool"
            percentage = a.Percentage if a.Percentage else "Unknown Percentage"
            desc = a.AssessmentDescription if a.AssessmentDescription else ""
            details.append(f"{tool} ({percentage}%): {desc}")
        return "Assessment details:\n" + "\n".join(details)
    return "No assessment details available."

# 23. Which courses are offered in {program} during {term}?
def query_courses_in_program_term(params):
    program_param = sanitize_id(params.get("program", ""))
    term_param = sanitize_id(params.get("term", ""))
    courses_found = []
    # Search for the program
    progs = onto.search(iri=f"*#{program_param}")
    if progs:
        program = progs[0]
        # Find term within this program matching term_param
        term = next((t for t in program.hasTerm if term_param in t.name), None)
        if term:
            for course in term.hasCourse:
                meta = get_course_metadata(course)
                if meta and meta.CourseCodeTitle:
                    courses_found.append(meta.CourseCodeTitle)
            if courses_found:
                return f"Courses offered in {params.get('program')} during term {params.get('term')}: {', '.join(courses_found)}."
    return "No courses found for the specified program and term."

# 24. Which instructors are associated with the {program} program or {term}?
def query_instructors_in_program_term(params):
    instructors_set = set()
    if "program" in params:
        program_param = sanitize_id(params.get("program", ""))
        progs = onto.search(iri=f"*#{program_param}")
        if progs:
            program = progs[0]
            for term in program.hasTerm:
                for course in term.hasCourse:
                    for ins in course.hasInstructorDetails:
                        if ins.Instructors:
                            instructors_set.add(ins.Instructors)
    elif "term" in params:
        term_param = sanitize_id(params.get("term", ""))
        terms = onto.search(iri=f"*#{term_param}")
        if terms:
            term = terms[0]
            for course in term.hasCourse:
                for ins in course.hasInstructorDetails:
                    if ins.Instructors:
                        instructors_set.add(ins.Instructors)
    if instructors_set:
        return f"Instructors: {', '.join(instructors_set)}"
    return ERROR_TEMPLATES["no_data"].format(data_type="instructors", entity="program/term", name=params.get("program") or params.get("term"))



# 26. Which assessment tool has the highest percentage weight in {course}?
def query_highest_assessment_tool(params):
    course = get_course(params.get("courseName", ""))
    if course and course.hasAssessment:
        highest = None
        for a in course.hasAssessment:
            # Extract numeric value from percentage string (e.g., "20%" → 20.0)
            percentage_str = a.Percentage or ""
            match = re.search(r'(\d+\.?\d*)', percentage_str)  # Find first number
            if not match:
                continue  # Skip invalid entries
            
            perc = float(match.group(1))
            if highest is None or perc > highest[0]:
                highest = (perc, a.AssessmentTool)
                
        if highest:
            return f"Highest weighted assessment tool: {highest[1]} ({highest[0]}%)."
    return ERROR_TEMPLATES["no_data"].format(data_type="assessment tool", entity="course", name=params.get("courseName"))

# 27. What are the consultation hours or contact details for the instructor of {course}?
def query_consultation_contact(params):
    course = get_course(params.get("courseName", ""))
    if course and course.hasInstructorDetails:
        instructor = course.hasInstructorDetails[0]
        if instructor.ContactDetails or instructor.ConsultationHours:
            return f"Contact: {instructor.ContactDetails}, Consultation Hours: {instructor.ConsultationHours}"
    return ERROR_TEMPLATES["no_data"].format(data_type="consultation details", entity="instructor", name=params.get("courseName"))

# 28. What is the office location of the instructor for {course}?
def query_instructor_office(params):
    course = get_course(params.get("courseName", ""))
    if course and course.hasInstructorDetails:
        instructor = course.hasInstructorDetails[0]
        if instructor.Office:
            return f"Office location: {instructor.Office}"
    return ERROR_TEMPLATES["no_data"].format(data_type="office location", entity="instructor", name=params.get("courseName"))

# 29. Which courses does {instructor} teach in the {program} program?
def query_courses_by_instructor_in_program(params):
    instructor_name = params.get("instructorName", "")
    program_param = sanitize_id(params.get("program", ""))
    inst = get_instructor(instructor_name)
    courses_found = []
    if inst and hasattr(inst, "teachesCourse"):
        for course in inst.teachesCourse:
            if course.belongsToTerm and course.belongsToTerm[0].belongsToProgram:
                prog = course.belongsToTerm[0].belongsToProgram[0]
                if program_param in prog.name:
                    meta = get_course_metadata(course)
                    if meta and meta.CourseCodeTitle:
                        courses_found.append(meta.CourseCodeTitle)
        if courses_found:
            return f"Courses taught by {instructor_name} in {params.get('program')}: {', '.join(courses_found)}."
        else:
            return ERROR_TEMPLATES["no_data"].format(data_type="courses", entity="instructor", name=instructor_name)
    return ERROR_TEMPLATES["not_found"].format(entity="instructor", name=instructor_name)

# 30. What topics are taught in {course}? (Full session plan)
def query_full_session_plan(params):
    course = get_course(params.get("courseName", ""))
    if course and course.hasSessionPlan:
        try:
            sessions = sorted(course.hasSessionPlan, key=lambda x: int(x.Session))
        except Exception:
            sessions = course.hasSessionPlan
        topics = [
            f"Session {s.Session}: {s.Module} - {s.Topic} (Materials: {s.ReadingMaterial})"
            for s in sessions if s.Topic and s.Topic != "NA"
        ]
        if topics:
            return "Course topics:\n" + "\n".join(topics)
    return ERROR_TEMPLATES["no_data"].format(data_type="session plan", entity="course", name=params.get("courseName"))

# =====================
# Generic Handlers (for reuse)
# =====================
def handle_standard_query(params, property_path, data_type, entity_name="course"):
    course = get_course(params.get("courseName", ""))
    if not course:
        return ERROR_TEMPLATES["not_found"].format(entity=entity_name, name=params.get("courseName"))
    value = get_nested_property(course, property_path)
    if not value:
        return ERROR_TEMPLATES["no_data"].format(data_type=data_type, entity=entity_name, name=params.get("courseName"))
    return str(value)

def handle_list_query(params, property_path, items_name, format_func=None):
    course = get_course(params.get("courseName", ""))
    if not course:
        return ERROR_TEMPLATES["not_found"].format(entity="course", name=params.get("courseName"))
    first_prop, *rest = property_path.split('.')
    results = getattr(course, first_prop, [])
    items = []
    if rest:
        nested_path = '.'.join(rest)
        for item in results:
            value = get_nested_property(item, nested_path)
            if value:
                items.append(format_func(value) if format_func else value)
    else:
        items = [format_func(item) if format_func else item for item in results if item]
    page = int(params.get("page", 0))
    pages = paginate_items(items)
    if not pages:
        return ERROR_TEMPLATES["no_data"].format(data_type=items_name, entity="course", name=params.get("courseName"))
    page = max(0, min(page, len(pages)-1))
    response = "\n".join(pages[page])
    if len(pages) > 1:
        response += ERROR_TEMPLATES["pagination"].format(current=page+1, total=len(pages))
    return response

# =====================
# Dispatch Dictionary for Intents
# =====================
INTENT_HANDLERS = {
    # Course Metadata
    "GetCourseCredits": lambda p: handle_standard_query(p, "hasCourseMetadata.CourseCredit", "credit information"),
    "GetCourseType": lambda p: handle_standard_query(p, "hasCourseMetadata.CourseType", "course type"),
    "GetPrerequisites": lambda p: handle_standard_query(p, "hasCourseMetadata.Prerequisites", "prerequisites"),
    "GetSessionDuration": lambda p: handle_standard_query(p, "hasCourseMetadata.SessionDuration", "session duration"),
    "GetTotalSessions": lambda p: handle_standard_query(p, "hasCourseMetadata.TotalSessions", "total sessions"),
    
    # Basic Info
    "GetCourseOverview": lambda p: handle_standard_query(p, "hasBasicInfo.Introduction", "course overview"),
    "GetLearningOutcomes": lambda p: handle_standard_query(p, "hasBasicInfo.LearningOutcomes", "learning outcomes"),
    "GetPedagogy": lambda p: handle_standard_query(p, "hasBasicInfo.PedagogyUsed", "pedagogy information"),
    
    # Instructor Info
    "GetInstructorForCourse": lambda p: handle_list_query(p, "hasInstructorDetails", "instructors", lambda i: get_nested_property(i, "Instructors")),
    "GetInstructorContact": lambda p: handle_standard_query(p, "hasInstructorDetails.ContactDetails", "contact details"),
    "GetContactInstructor": query_contact_instructor,   # Query 11
    "GetCoursesByInstructor": query_courses_by_instructor,  # Query 12
    
    # Sessions and Topics
    "GetCourseTopics": lambda p: handle_list_query(p, "hasSessionPlan", "topics", lambda s: f"Session {s.Session}: {s.Module} - {s.Topic}"),
    "GetSessionInfo": lambda p: handle_standard_query(p, f"hasSessionPlan.{p.get('sessionNumber')}", "session info"),
    "GetFullSessionPlan": query_full_session_plan,       # Query 30
    
    # Assessments
    "GetAssessmentTools": lambda p: handle_list_query(p, "hasAssessment", "assessment tools", lambda a: a.AssessmentTool),
    "GetAssessmentPercentage": query_assessment_percentage,  # Queries 5 & 14
    "GetAssessmentDetails": query_assessment_details_full,  # Query 22
    "GetHighestAssessmentTool": query_highest_assessment_tool,  # Query 26
    
    # Additional Course Metadata queries
    "GetYearBatch": query_year_batch,    # Query 16
    "GetSections": query_sections,         # Query 17
    
    # Program/Term related queries
    "GetProgramForCourse": query_program_for_course,          # Query 2
    "GetTermForCourseProgram": query_term_for_course_program,   # Query 3
    "GetCoursesInProgramTerm": query_courses_in_program_term,   # Query 23
    "GetInstructorsInProgramTerm": query_instructors_in_program_term,  # Query 24

    # Instructor additional queries
    "GetInstructorOffice": query_instructor_office,           # Query 28
    "GetCoursesByInstructorInProgram": query_courses_by_instructor_in_program,  # Query 29
    "GetConsultationContact": query_consultation_contact,     # Query 27
}

# =====================
# Webhook Endpoint
# =====================
@app.route('/webhook', methods=['POST'])
def webhook():
    try:
        req = request.get_json()
        intent = req.get("queryResult", {}).get("intent", {}).get("displayName", "")
        params = req.get("queryResult", {}).get("parameters", {})
        logging.info(f"Received params: {params}")
        contexts = req.get("queryResult", {}).get("outputContexts", [])

        # Handle pagination context if exists
        page_context = next((c for c in contexts if "parameters" in c and "page" in c["parameters"]), {})
        page = page_context.get("parameters", {}).get("page", 0)
        params["page"] = page

        handler = INTENT_HANDLERS.get(intent)
        if not handler:
            return jsonify({"fulfillmentText": "This query type is not supported yet."})

        response_text = handler(params)

        # Prepare pagination context output if applicable
        output_contexts = []
        if "page" in params:
            output_contexts.append({
                "name": f"projects/${{projectId}}/agent/sessions/${{sessionId}}/contexts/pagination",
                "lifespanCount": 5,
                "parameters": {
                    "page": params.get("page", 0),
                    "original_query": json.dumps(params)
                }
            })

        return jsonify({
            "fulfillmentText": response_text,
            "outputContexts": output_contexts
        })

    except Exception as e:
        logging.error(f"Error processing request: {str(e)}")
        return jsonify({"fulfillmentText": "Sorry, I encountered an error processing your request."})

if __name__ == '__main__':
    app.run(port=5000, debug=True)
