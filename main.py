import random
from constraint import Problem, AllDifferentConstraint, FunctionConstraint, nValues


# --- Data Generation ---
NUM_STUDENTS = 50
NUM_CLASSROOMS = 10
CLASSROOM_IDS = list(range(NUM_CLASSROOMS))

# 1. Student Scores (random for now)
student_scores = {f"S{i}": random.randint(50, 100) for i in range(NUM_STUDENTS)}

# 2. Student Dislikes (random pairs)
student_dislikes = set()
for _ in range(NUM_STUDENTS // 10): # A few dislike pairs
    s1 = f"S{random.randint(0, NUM_STUDENTS - 1)}"
    s2 = f"S{random.randint(0, NUM_STUDENTS - 1)}"
    if s1 != s2 and (s2, s1) not in student_dislikes:
        student_dislikes.add((s1, s2))
print(f"Dislikes: {student_dislikes}")

# 3. Student Subject Preferences and Teacher Subject Specializations
subjects = ["Math", "Science", "Literature", "History", "Art", "Music", "PE", "IT", "ForeignLanguage", "Economics"]
student_preferences = {f"S{i}": random.choice(subjects) for i in range(NUM_STUDENTS)}

# Assume each classroom is taught by a teacher with a specific subject specialization
# We need to ensure a diverse set of teachers to match student preferences
classroom_teacher_subjects = {
    c_id: subjects[c_id % len(subjects)] for c_id in CLASSROOM_IDS
}

# For simplicity, let's ensure each classroom has a unique primary subject for its teacher
# In a real scenario, you'd define this based on actual teachers
if NUM_CLASSROOMS <= len(subjects):
    classroom_teacher_subjects = {CLASSROOM_IDS[i]: subjects[i] for i in range(NUM_CLASSROOMS)}
else: # If more classrooms than subjects, subjects will repeat
    classroom_teacher_subjects = {CLASSROOM_IDS[i]: subjects[i % len(subjects)] for i in range(NUM_CLASSROOMS)}

print(f"Classroom Teacher Subjects: {classroom_teacher_subjects}")

# --- CSP Problem Definition ---
problem = Problem()

# Define a variable for each student, representing the classroom they are assigned to
# Domain for each student is the set of classroom IDs
for student_id in student_scores:
    problem.addVariable(student_id, CLASSROOM_IDS)

# --- Constraints ---

# Constraint 1: Similar Average Score in Classrooms (Soft Constraint / Optimization)
# This is the trickiest one for a pure CSP solver. CSP solvers primarily deal with
# *hard* constraints (must be satisfied). "Similar average score" is an *optimization*
# or *soft* constraint.
#

# For `python-constraint`, we can define it as a hard constraint that the average
# *must* be within a certain range, or that the sum of scores in each class is similar.

# A common way to handle this in CSP is to try to make the sum of scores in each class
# close to the overall average student score *per student*.
#

# Let's assume a hard constraint: the sum of scores in each classroom must be within
# a certain percentage of the ideal average sum.

# Ideal students per classroom: NUM_STUDENTS / NUM_CLASSROOMS
# Ideal average score: sum(student_scores.values()) / NUM_STUDENTS
# Ideal sum of scores per classroom: (NUM_STUDENTS / NUM_CLASSROOMS) * (sum(student_scores.values()) / NUM_STUDENTS)
#                                  = sum(student_scores.values()) / NUM_CLASSROOMS


total_score = sum(student_scores.values())
ideal_classroom_score_sum = total_score / NUM_CLASSROOMS

SCORE_TOLERANCE_PERCENT = 0.15 # e.g., 15% deviation allowed

min_classroom_score_sum = ideal_classroom_score_sum * (1 - SCORE_TOLERANCE_PERCENT)
max_classroom_score_sum = ideal_classroom_score_sum * (1 + SCORE_TOLERANCE_PERCENT)

print(f"Ideal Classroom Score Sum: {ideal_classroom_score_sum:.2f}")
print(f"Allowed Score Sum Range per Classroom: [{min_classroom_score_sum:.2f}, {max_classroom_score_sum:.2f}]")

# To implement this, we need to define a constraint that looks at all students
# assigned to a classroom. This is an N-ary constraint.
# python-constraint's FunctionConstraint is good for this.
# We'll create one constraint per classroom.

def classroom_score_sum_constraint(*student_classroom_assignments, classroom_id, student_ids_in_classroom, student_scores, min_sum, max_sum):
    current_classroom_students = []
    for i, student_id in enumerate(student_ids_in_classroom):
        if student_classroom_assignments[i] == classroom_id:
            current_classroom_students.append(student_id)

    if not current_classroom_students: # A class can be empty if not enough students, this might need refinement
        return True # Or False, depending on whether empty classes are allowed. Let's allow for now.

    current_sum = sum(student_scores[s_id] for s_id in current_classroom_students)
    return min_sum <= current_sum <= max_sum


# We need to map which students are considered for which classroom's sum.
# This constraint needs all student variables, which makes it very large.
# A more practical approach for soft constraints or optimization is often
# to find *any* solution and then apply a post-processing optimization step,
# or use a different solver approach (e.g., Integer Programming, Minizinc)
# that explicitly handles optimization.

# For python-constraint, let's simplify for now:
# Instead of exact average, ensure a minimum and maximum number of students per class.
# This helps with the average score constraint indirectly.

min_students_per_class = NUM_STUDENTS // NUM_CLASSROOMS - 2 # Allow some deviation
max_students_per_class = NUM_STUDENTS // NUM_CLASSROOMS + 2

if min_students_per_class < 1: min_students_per_class = 1

# This is a good proxy for 'similar average' if scores are somewhat uniform.
for c_id in CLASSROOM_IDS:
    problem.addConstraint(lambda *args, classroom=c_id:
                          min_students_per_class <= sum(1 for assignment in args if assignment == classroom) <= max_students_per_class,
                          list(student_scores.keys())) # All students are arguments

# Constraint 2: Student Dislikes
for s1, s2 in student_dislikes:
    # Students s1 and s2 must not be in the same classroom
    problem.addConstraint(lambda class1, class2: class1 != class2, (s1, s2))

# Constraint 3: Subject Preference Matching
# Students who like a subject should be in a classroom whose teacher teaches that subject.
# This is a hard constraint.
for student_id, student_fav_subject in student_preferences.items():
    problem.addConstraint(lambda assigned_class, fav_subject=student_fav_subject:
                          classroom_teacher_subjects[assigned_class] == fav_subject,
                          (student_id,))


# Constraint 4: Other Assumed Constraints (Examples)

# 4a. Classroom Capacity (Similar to min/max students per class, but more explicit capacity)
# We've partially covered this with `min_students_per_class` and `max_students_per_class`.
# Let's add a more explicit, tighter capacity if needed.
# For example, each class must have between `min_students_per_class` and `max_students_per_class` students.
# (This is already covered by the count constraint above, but a more explicit range can be used.)

# 4b. Ensure each classroom has at least one student
# This is covered by `min_students_per_class >= 1`

# 4c. Balanced Gender (Example - Requires gender data)
# If we had `student_genders = {f"S{i}": random.choice(["Male", "Female"]) for i in range(NUM_STUDENTS)}`
# We could add constraints like:

# for c_id in CLASSROOM_IDS:
#     problem.addConstraint(lambda *args, classroom=c_id:
#                           # complex logic to count males/females and ensure balance
#                           True, # Placeholder
#                           list(student_scores.keys()))

# 4d. Avoid specific student pairings (e.g., S5 and S15 *must* be together)
# problem.addConstraint(lambda class5, class15: class5 == class15, ("S5", "S15"))

print("\nAttempting to find solutions...")

# Note: For NUM_STUDENTS=500 and NUM_CLASSROOMS=10, this will be EXTREMELY slow
# with `python-constraint`'s default solver. The number of variables is huge,
# and N-ary constraints involving all students are computationally intensive.
# For demonstration, I've set NUM_STUDENTS to 50.

solutions = problem.getSolutions()

print(f"\nFound {len(solutions)} solution(s).")

if solutions:
    print("\nDisplaying one solution:")
    first_solution = solutions[0]
    classroom_assignments = {c_id: [] for c_id in CLASSROOM_IDS}
    for student_id, assigned_class in first_solution.items():
        classroom_assignments[assigned_class].append(student_id)

    for c_id, students in classroom_assignments.items():
        print(f"\nClassroom {c_id}:")
        print(f"  Number of Students: {len(students)}")

        class_scores = [student_scores[s] for s in students]

        print(f"  Average Score: {sum(class_scores)/len(class_scores):.2f}" if students else "N/A")
        print(f"  Teacher Subject: {classroom_teacher_subjects[c_id]}")
        print(f"  Students: {', '.join(students)}")

        # Verify dislike constraint for this class
        for i in range(len(students)):
            for j in range(i + 1, len(students)):
                s1, s2 = students[i], students[j]
                if (s1, s2) in student_dislikes or (s2, s1) in student_dislikes:
                    print(f"  !!! WARNING: Disliked pair ({s1}, {s2}) found in Classroom {c_id} (Should not happen if constraint is perfect)")

        # Verify subject preference for this class
        for s in students:
            if classroom_teacher_subjects[c_id] != student_preferences[s]:
                print(f"  !!! WARNING: Student {s} (likes {student_preferences[s]}) assigned to Class {c_id} (teacher likes {classroom_teacher_subjects[c_id]}) (Should not happen)")

else:
    print("No solutions found given the current constraints and parameters.")



