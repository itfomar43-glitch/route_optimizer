from ortools.sat.python import cp_model
from datetime import datetime, timedelta
from collections import defaultdict
import random

# --------------------------
# 1) إعداد بيانات واقعية
# --------------------------
random.seed(0)

# كامبات: اسم، عدد الباصات المتوفرة، مدة الرحلة التقريبية (دقائق)
camps = {
    "CampA": {"num_buses": 3, "trip_min": 30},
    "CampB": {"num_buses": 2, "trip_min": 35},
    "CampC": {"num_buses": 2, "trip_min": 25},
}

# شيفتات: معرف -> (اسم عرضي, start_hour, end_hour)
shifts = {
    "S1": ("صباحي 8-12", 8, 12),
    "S2": ("صباحي متأخر 10-14", 10, 14),
    "S3": ("مسائي 12-16", 12, 16),
    "S4": ("مسائي متأخر 14-18", 14, 18),
}

BUS_CAPACITY = 14
BUFFER_MIN = 10  # دقايق احتياطي قبل وبعد

# نولد بيانات خادمات واقعية (مثال: 60 خادمة موزعين على الكامبات والشيفتات)
maids = []
maid_id = 1
# توزيع تقريبي: CampA أكثر (30)، CampB (18)، CampC (12) = 60
for camp, count in [("CampA", 30), ("CampB", 18), ("CampC", 12)]:
    for _ in range(count):
        # نوزع الشيفتات عشوائياً لكن واقعيًا (أغلبهم في الصباح)
        shift_key = random.choices(list(shifts.keys()), weights=[0.45, 0.25, 0.2, 0.1], k=1)[0]
        maids.append({
            "id": f"M{maid_id}",
            "name": f"maid{maid_id}",
            "camp": camp,
            "shift": shift_key
        })
        maid_id += 1

# --------------------------
# 2) إنشاء قائمة الباصات (حقيقية) لكل كامب
# --------------------------
buses = []
for camp_name, info in camps.items():
    for i in range(info["num_buses"]):
        buses.append({
            "id": f"{camp_name}_bus{i+1}",
            "camp": camp_name,
            "capacity": BUS_CAPACITY,
            "trip_min": info["trip_min"]
        })

# --------------------------
# 3) نموذج CP-SAT: المتغيرات والقيود
# --------------------------
model = cp_model.CpModel()
num_maids = len(maids)
num_buses = len(buses)
shift_keys = list(shifts.keys())

# متغيرات الاسناد: assign[(r_idx, b_idx)] = True إذا المايد r اتعيّنت للباص b لشيفتها
assign = {}
for r in range(num_maids):
    for b in range(num_buses):
        assign[(r, b)] = model.NewBoolVar(f"assign_r{r}_b{b}")

# متغير serve[b,s] : هل الباص b يخدم الشيفت s (يعمل رحلة لهذا الشيفت)
serve = {}
for b in range(num_buses):
    for s in shift_keys:
        serve[(b, s)] = model.NewBoolVar(f"serve_b{b}_{s}")

# متغير bus_used[b]
bus_used = [model.NewBoolVar(f"bus_used_{b}") for b in range(num_buses)]

# قيد 1: كل خادمة لازم تتعيّن مرة واحدة لباص واحد (داخل كامبها)
for r_idx, r in enumerate(maids):
    allowed = []
    for b_idx, bus in enumerate(buses):
        if bus["camp"] == r["camp"]:
            allowed.append(assign[(r_idx, b_idx)])
        else:
            # ممنوع تعيين لباص من كامب تاني
            model.Add(assign[(r_idx, b_idx)] == 0)
    # لابد أن تكون معرّفة على باص واحد
    model.Add(sum(allowed) == 1)

# قيد 2: ربط assign مع serve: لو assign[r,b] = 1 => serve[b, shift_of_r] = 1
for r_idx, r in enumerate(maids):
    s = r["shift"]
    for b_idx, bus in enumerate(buses):
        model.AddImplication(assign[(r_idx, b_idx)], serve[(b_idx, s)])

# قيد 3: سعة الباص لكل شيفت: مجموع المعينين للباص b ولشيفت s <= capacity
for b_idx, bus in enumerate(buses):
    for s in shift_keys:
        assigns_for_bs = [assign[(r_idx, b_idx)] for r_idx, r in enumerate(maids) if r["shift"] == s and r["camp"] == bus["camp"]]
        if assigns_for_bs:
            model.Add(sum(assigns_for_bs) <= bus["capacity"])
        else:
            # لا حاجة، لا يوجد طلبات لذلك الشيفت على هذا الباص/كامب
            pass

# قيد 4: serve variables درست كما: serve[b,s] = True iff أي assign[r,b] موجود للشيفت s
for b_idx, bus in enumerate(buses):
    for s in shift_keys:
        assigns_for_bs = [assign[(r_idx, b_idx)] for r_idx, r in enumerate(maids) if r["shift"] == s and r["camp"] == bus["camp"]]
        if assigns_for_bs:
            # إذا serve True → مجموع assigns >= 1
            model.Add(sum(assigns_for_bs) >= 1).OnlyEnforceIf(serve[(b_idx, s)])
            # إذا serve False → مجموع assigns == 0
            model.Add(sum(assigns_for_bs) == 0).OnlyEnforceIf(serve[(b_idx, s)].Not())
        else:
            model.Add(serve[(b_idx, s)] == 0)

# قيد 5: عدم التداخل الزمني للشيفتات على نفس الباص
def shifts_overlap(s1, s2):
    a1, b1 = shifts[s1][1], shifts[s1][2]
    a2, b2 = shifts[s2][1], shifts[s2][2]
    return not (b1 <= a2 or b2 <= a1)

for b_idx in range(num_buses):
    for i in range(len(shift_keys)):
        for j in range(i+1, len(shift_keys)):
            s1 = shift_keys[i]; s2 = shift_keys[j]
            if shifts_overlap(s1, s2):
                # لا يمكن أن يخدم الباص الشيفتين المتداخلتين معًا
                model.AddBoolOr([serve[(b_idx, s1)].Not(), serve[(b_idx, s2)].Not()])

# قيد 6: ربط serve مع bus_used
for b_idx in range(num_buses):
    # إذا أي serve[b, s] True -> bus_used True
    for s in shift_keys:
        model.AddImplication(serve[(b_idx, s)], bus_used[b_idx])
    # إذا bus_used True -> على الأقل serve واحد True
    model.AddBoolOr([serve[(b_idx, s)] for s in shift_keys]).OnlyEnforceIf(bus_used[b_idx])

# الهدف: تصغير عدد الباصات المستخدمة
model.Minimize(sum(bus_used))

# --------------------------
# 4) حل النموذج
# --------------------------
solver = cp_model.CpSolver()
solver.parameters.max_time_in_seconds = 20  # وقت حل معقول
solver.parameters.num_search_workers = 8

status = solver.Solve(model)

# --------------------------
# 5) استخراج النتائج وعرض جدول ذهاب/عودة مفصل
# --------------------------
if status in (cp_model.OPTIMAL, cp_model.FEASIBLE):
    # تجميع التعيينات حسب باص ثم شيفت
    result = defaultdict(lambda: defaultdict(list))  # result[bus_id][shift] = [maid names]
    used_buses = []
    for b_idx, bus in enumerate(buses):
        if solver.Value(bus_used[b_idx]) == 1:
            used_buses.append(b_idx)
        for r_idx, r in enumerate(maids):
            if solver.Value(assign[(r_idx, b_idx)]) == 1:
                result[b_idx][r["shift"]].append(r["name"])

    # طباعة ملخص
    print("==== خطة الحافلات (تفصيل شيفتات لكل باص والركاب) ====\n")
    for b_idx in range(num_buses):
        bus = buses[b_idx]
        if solver.Value(bus_used[b_idx]) == 0:
            continue
        print(f"🚌 {bus['id']} | كامب: {bus['camp']} | سعة: {bus['capacity']}")
        # لكل شيفت اللي الباص خدمها (مرتبة زمنياً)
        served_shifts = [s for s in shift_keys if solver.Value(serve[(b_idx, s)]) == 1]
        # نحسب أوقات الانطلاق والعودة لكل شيفت
        for s in sorted(served_shifts, key=lambda x: shifts[x][1]):
            shift_name, start_h, end_h = shifts[s]
            trip_min = bus["trip_min"]
            depart = (datetime(2025,10,2,start_h,0) - timedelta(minutes=trip_min + BUFFER_MIN)).time()
            ret = (datetime(2025,10,2,end_h,0) + timedelta(minutes=trip_min + BUFFER_MIN)).time()
            assigned = result[b_idx][s]
            print(f"   ▶ الشيفت: {shift_name} ({start_h}:00 - {end_h}:00)")
            print(f"       الركاب ({len(assigned)}): {', '.join(assigned)}")
            print(f"       انطلاق (مقدّر): {depart} | عودة (مقدّر): {ret}")
        print("-" * 60)
    print(f"\nمجموع الباصات المستخدمة: {sum(int(solver.Value(b)) for b in bus_used)}")
else:
    print("لم يتم إيجاد حل خلال الوقت المسموح أو لا يوجد حل.")
