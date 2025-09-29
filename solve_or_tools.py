import pandas as pd
from ortools.sat.python import cp_model
import math
import os
import random
from datetime import datetime

def solve_classroom_assignment_from_csv(file_path="csp_problem.csv"):    
    # --- 1. Load CSV file ---
    try:
        df = pd.read_csv(file_path)
    except FileNotFoundError:
        print(f"Error: '{file_path}' Failed to load file.")
        return

    # column 이름 매핑
    column_mapping = {
        'sex': 'gender',
        '24년 학급': 'last_year_class',
        '클럽': 'club',
        '좋은관계': 'good_relation',
        '나쁜관계': 'bad_relation',
        'Leadership': 'is_leader',
        'Piano': 'plays_piano',
        '비등교': 'is_truant',
        '운동선호': 'is_athletic'
    }
    df.rename(columns=column_mapping, inplace=True)

    # 데이터 타입 변환 및 정리
    # yes는 1로, 빈칸(NaN)은 0으로 변환
    for col in ['is_leader', 'plays_piano', 'is_truant', 'is_athletic']:
        df[col] = df[col].apply(lambda x: 1 if x == 'yes' else 0)
    
    # 관계 데이터에서 빈칸(NaN)을 -1로 변환 - 해당 column에 값이 있는 학생과 구분하기 위함
    for col in ['good_relation', 'bad_relation']:
        df[col] = pd.to_numeric(df[col], errors='coerce').fillna(-1).astype(int)

    NUM_CLASSES = 6
    STUDENT_IDS = df['id'].tolist()

    # 34명이 될 반 2개를 random하게 선택
    CLASS_IDS = list(range(NUM_CLASSES)) # [0, 1, 2, 3, 4, 5]

    large_CLASS_IDS = random.sample(CLASS_IDS, 2)
    CLASS_SIZES = {}
    for class_id in CLASS_IDS:
        if class_id in large_CLASS_IDS:
            CLASS_SIZES[class_id] = 34
        else:
            CLASS_SIZES[class_id] = 33
    print("이번 실행의 반별 정원:", CLASS_SIZES) # 실행시마다 정원이 바뀌게 해놓음

    # --- 2. 모델 생성 ---
    model = cp_model.CpModel()

    # --- 3. 변수 정의 ---
    student_class = {student_id: model.NewIntVar(0, NUM_CLASSES - 1, f'student_{student_id}_class') for student_id in STUDENT_IDS}
    assign = {student_id: {class_id: model.NewBoolVar(f'assign_{student_id}_to_{class_id}') for class_id in CLASS_IDS} for student_id in STUDENT_IDS}

    # --- 4. 기본 제약 조건 ---
    for student_id in STUDENT_IDS:
        model.AddExactlyOne([assign[student_id][class_id] for class_id in CLASS_IDS])
        for class_id in CLASS_IDS:
            model.Add(student_class[student_id] == class_id).OnlyEnforceIf(assign[student_id][class_id])

    for class_id, size in CLASS_SIZES.items():
        model.Add(sum(assign[student_id][class_id] for student_id in STUDENT_IDS) == size)

    # --- 5. 과제 요구사항 제약 조건 구현 부분 ---

    # 제약 1-A: '나쁜관계' 학생들은 다른 반으로 배정
    for _, row in df[df['bad_relation'] != -1].iterrows():
        s1, s2 = int(row['id']), int(row['bad_relation'])
        if s2 in student_class: # 데이터에 존재하는 학생 ID인지 확인
            model.Add(student_class[s1] != student_class[s2])

    # 제약 1-B: 비등교 학생은 좋은 관계의 친구와 같은 반으로 배정
    truant_students_df = df[df['is_truant'] == 1]
    for _, row in truant_students_df[truant_students_df['good_relation'] != -1].iterrows():
        s1_truant = int(row['id'])
        s2_friend = int(row['good_relation'])
        if s2_friend in student_class:
            model.Add(student_class[s1_truant] == student_class[s2_friend])

    # 제약 2: 각 반에 리더십 학생이 최소 1명 이상 배정 + 너무 치우치지 않게 커스텀하였음
    leader_ids = df[df['is_leader'] == 1]['id'].tolist()
    max_leaders_per_class = 5 
    for class_id in CLASS_IDS:
        model.Add(sum(assign[student_id][class_id] for student_id in leader_ids) >= 1)
        model.Add(sum(assign[student_id][class_id] for student_id in leader_ids) <= max_leaders_per_class)

    # 제약 3, 5, 7: 피아노, 비등교, 운동선호 학생 균등 분배
    for feature in ['plays_piano', 'is_truant', 'is_athletic']:
        student_ids_with_feature = df[df[feature] == 1]['id'].tolist()
        total_count = len(student_ids_with_feature)
        min_per_class = total_count // NUM_CLASSES
        max_per_class = math.ceil(total_count / NUM_CLASSES)
        for class_id in CLASS_IDS:
            model.AddLinearConstraint(sum(assign[student_id][class_id] for student_id in student_ids_with_feature), min_per_class, max_per_class)
    
    # 제약 6: 성비 균등 분배
    male_ids = df[df['gender'] == 'boy']['id'].tolist()
    min_males = len(male_ids) // NUM_CLASSES
    max_males = math.ceil(len(male_ids) / NUM_CLASSES)
    for class_id in CLASS_IDS:
        model.AddLinearConstraint(sum(assign[student_id][class_id] for student_id in male_ids), min_males, max_males)

    # 제약 4: 성적 균등 분배 (반별 총점 편차 최소화)
    total_score = df['score'].sum()
    avg_score_per_class = total_score / NUM_CLASSES
    tolerance = avg_score_per_class * 0.05
    for class_id in CLASS_IDS:
        class_total_score = sum(assign[student_id][class_id] * df.loc[df['id'] == student_id, 'score'].iloc[0] for student_id in STUDENT_IDS)
        model.AddLinearConstraint(class_total_score, int(avg_score_per_class - tolerance), int(avg_score_per_class + tolerance))

    # 제약 8: 전년도 클래스 메이트 분산
    last_year_classes = df['last_year_class'].dropna().unique()
    max_overlap = 7
    for last_c in last_year_classes:
        students_from_last_class = df[df['last_year_class'] == last_c]['id'].tolist()
        for class_id in CLASS_IDS:
            model.Add(sum(assign[student_id][class_id] for student_id in students_from_last_class) <= max_overlap)

    # 제약 9: 클럽 활동 멤버 균등 분배
    all_clubs = df['club'].dropna().unique()
    for club in all_clubs:
        member_ids = df[df['club'] == club]['id'].tolist()
        min_mems = len(member_ids) // NUM_CLASSES
        max_mems = math.ceil(len(member_ids) / NUM_CLASSES)
        for class_id in CLASS_IDS:
            model.AddLinearConstraint(sum(assign[student_id][class_id] for student_id in member_ids), min_mems, max_mems)

    # --- 6. 솔버 실행 ---
    print("Searching for solutions...")
    solver = cp_model.CpSolver()
    solver.parameters.max_time_in_seconds = 60.0
    status = solver.Solve(model)

    # --- 7. 결과 출력 및 저장 ---
    if status in (cp_model.OPTIMAL, cp_model.FEASIBLE):
        print(f"\n Find a solution! (Status: {solver.StatusName(status)})")
        
        # 배정 결과를 DataFrame에 추가 (0~5 -> 1~6반으로 표시)
        df['assigned_class'] = df['id'].apply(lambda student_id: solver.Value(student_class[student_id]) + 1)

        print("\n--- [ Terminal Output: Class Summary ] ---")
        for class_id in sorted(df['assigned_class'].unique()):
            class_df = df[df['assigned_class'] == class_id]
            print(f"\n [ {class_id}반: {len(class_df)}명 ]")
            print(f"  - 성적 평균: {class_df['score'].mean():.2f}")
            print(f"  - 남녀 비율: 남학생 {len(class_df[class_df['gender'] == 'boy'])}명 / 여학생 {len(class_df[class_df['gender'] == 'girl'])}명")
            print(f"  - 리더: {class_df['is_leader'].sum()}명")
            print(f"  - 피아노: {class_df['plays_piano'].sum()}명")
            print(f"  - 비등교: {class_df['is_truant'].sum()}명")
            print(f"  - 운동선호: {class_df['is_athletic'].sum()}명")
            print(f"  - 클럽 분포:")
            club_counts = class_df['club'].value_counts()
            for club, count in club_counts.items():
                print(f"    * {club}: {count}명")

        # or_tools.py 결과 CSV 파일로 저장
        output_dir = "or_tools_results"
        os.makedirs(output_dir, exist_ok=True) # 결과 저장 디렉토리 생성

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        output_filename = f"assignment_results_or-tools_{timestamp}.csv"
        full_path = os.path.join(output_dir, output_filename)
        
        # 필요한 컬럼만 선택하여 저장
        results_df = df[['id', 'name', 'assigned_class', 'score', 'gender', 'club', 'is_leader', 'plays_piano']]
        results_df.to_csv(full_path, index=False, encoding='utf-8-sig')
        print(f"\n\n Results have been saved to '{output_filename}'.")

    else:
        print("\n Failed to find a solution.")


if __name__ == '__main__':
    solve_classroom_assignment_from_csv()