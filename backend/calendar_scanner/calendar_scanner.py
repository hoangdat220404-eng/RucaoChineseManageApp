# --- FILE: backend/calendar_scanner/scan_calendar.py (PHIÊN BẢN MỚI NHẤT) ---

import datetime
import os.path
import re
import json
from dateutil.parser import parse
from dateutil.relativedelta import relativedelta
from dateutil import parser
import threading
import copy
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from dateutil.parser import parse as dt_parse
data_lock = threading.Lock()



DAY_MAP = {"2": "MO", "3": "TU", "4": "WE", "5": "TH", "6": "FR", "7": "SA", "CN": "SU"}
# Ngược lại, để tìm ngày đầu tiên
DAY_TO_ISOWEEKDAY = {"2": 1, "3": 2, "4": 3, "5": 4, "6": 5, "7": 6, "CN": 7}

# --- THAM SỐ ---
SCOPES = ['https://www.googleapis.com/auth/calendar']



basedir = os.path.abspath(os.path.dirname(__file__))

SCAN_RANGE_COURSE_DAYS = 180
SCAN_RANGE_DAYS = 30
OUTPUT_BILL_JSON_PATH = os.path.join(os.path.dirname(__file__), 'data', 'bill.json')
DATA_BASE_PATH = os.path.join(basedir, '..','..', 'database', 'database.json')
TARGET_CALENDAR_ID = "classroom107849112838946582499@group.calendar.google.com" 


def delete_class_and_future_instances(class_name, Calendar_ID):
    """
    1. Quét 14 ngày tới.
    2. So sánh tên dạng 'chứa từ khóa' (flexible).
    3. Nếu là sự kiện lặp:
       - Nếu trùng ngày bắt đầu gốc: Xóa vĩnh viễn cả chuỗi.
       - Nếu nằm ở giữa: Cắt đuôi (Delete this and following).
    """
    print(f"\n--- BẮT ĐẦU QUÉT: '{class_name}' (14 ngày tới) ---")
    
    try:
        service = authenticate_google_calendar()
        
        # 1. Thiết lập thời gian quét
        now = datetime.datetime.utcnow()
        time_min = now.isoformat() + 'Z'
        time_max = (now + datetime.timedelta(days=14)).isoformat() + 'Z'

        # 2. Lấy danh sách (singleEvents=True để bung tất cả ra)
        events_result = service.events().list(
            calendarId=Calendar_ID,
            timeMin=time_min,
            timeMax=time_max,
            q=class_name, # Google lọc sơ bộ
            singleEvents=True,
            orderBy='startTime'
        ).execute()

        events = events_result.get('items', [])
        
        if not events:
            return False, f"Google không trả về kết quả nào cho từ khóa '{class_name}'."

        count_deleted = 0
        processed_master_ids = set() 

        print(f" -> Tìm thấy {len(events)} sự kiện tiềm năng. Đang lọc...")

        for event in events:
            summary = event.get('summary', '').strip()
            event_id = event['id']
            
            # --- LOGIC SO SÁNH TÊN (QUAN TRỌNG) ---
            # Chuyển hết về chữ thường để so sánh
            # Dùng 'in' thay vì '==' để bắt được trường hợp 'Rucao_GV_Lớp A'
            if class_name.lower() not in summary.lower():
                print(f"    [Bỏ qua] Tên không khớp: '{summary}'")
                continue

            # Lấy thời gian bắt đầu của Instance này
            start_raw = event['start'].get('dateTime') or event['start'].get('date')
            instance_start_dt = parser.parse(start_raw).astimezone(datetime.timezone.utc)
            
            print(f" -> Đang xử lý: '{summary}' vào ngày {start_raw}")

            # --- TRƯỜNG HỢP A: SỰ KIỆN LẶP LẠI ---
            if 'recurringEventId' in event:
                master_id = event['recurringEventId']
                
                if master_id in processed_master_ids:
                    # Đã xử lý chuỗi này rồi -> Instance này tự động biến mất, bỏ qua
                    continue

                try:
                    # Lấy Master Event gốc
                    master_event = service.events().get(calendarId=Calendar_ID, eventId=master_id).execute()
                    
                    # Lấy thời gian bắt đầu của MASTER (Gốc rễ)
                    master_start_raw = master_event['start'].get('dateTime') or master_event['start'].get('date')
                    master_start_dt = parser.parse(master_start_raw).astimezone(datetime.timezone.utc)

                    # SO SÁNH NGÀY: 
                    # Nếu Instance này trùng ngày với Master Gốc -> XÓA LUÔN MASTER
                    # (Dùng delta nhỏ < 24h để so sánh cho an toàn vì lệch giờ)
                    time_diff = abs((instance_start_dt - master_start_dt).total_seconds())
                    
                    if time_diff < 86400: # Chênh lệch ít hơn 1 ngày => Là buổi đầu tiên
                        print("    => Đây là buổi đầu tiên của chuỗi. Xóa vĩnh viễn cả chuỗi!")
                        service.events().delete(calendarId=Calendar_ID, eventId=master_id).execute()
                        processed_master_ids.add(master_id)
                        count_deleted += 1
                        continue

                    # Nếu không phải buổi đầu -> CẮT ĐUÔI (Sửa UNTIL)
                    print("    => Đây là buổi ở giữa. Cắt chuỗi từ đây.")
                    
                    # Tính toán UNTIL: Lùi lại 1 ngày so với Instance hiện tại
                    # Ví dụ: Xóa ngày 25 -> UNTIL = Hết ngày 24
                    until_dt = instance_start_dt - datetime.timedelta(days=1)
                    until_str = until_dt.strftime('%Y%m%dT%H%M%SZ')

                    recurrence_rules = master_event.get('recurrence', [])
                    new_recurrence = []
                    if recurrence_rules:
                        for rule in recurrence_rules:
                            if rule.startswith('RRULE:'):
                                rule = re.sub(r';?UNTIL=[^;]+', '', rule)
                                rule = re.sub(r';?COUNT=[^;]+', '', rule)
                                rule += f";UNTIL={until_str}"
                            new_recurrence.append(rule)
                        
                        master_event['recurrence'] = new_recurrence
                        service.events().update(calendarId=Calendar_ID, eventId=master_id, body=master_event).execute()
                        
                        processed_master_ids.add(master_id)
                        count_deleted += 1

                except Exception as ex:
                    print(f"    [Lỗi xử lý lặp] {ex}")

            # --- TRƯỜNG HỢP B: SỰ KIỆN ĐƠN LẺ ---
            else:
                try:
                    service.events().delete(calendarId=Calendar_ID, eventId=event_id).execute()
                    print("    => Đã xóa sự kiện đơn.")
                    count_deleted += 1
                except Exception as ex:
                    print(f"    [Lỗi xóa đơn] {ex}")

        # TỔNG KẾT
        if count_deleted > 0:
            msg = f"Thành công! Đã xử lý {count_deleted} sự kiện/chuỗi sự kiện '{class_name}'."
            return True, msg
        else:
            # Nếu chạy hết vòng lặp mà count vẫn = 0 -> Có sự kiện nhưng tên không khớp cái nào
            msg = f"Tìm thấy sự kiện nhưng tên không chứa từ khóa '{class_name}'."
            return False, msg

    except Exception as e:
        return False, f"Lỗi hệ thống: {str(e)}"
    """
    Tìm sự kiện 'class_name' trong 14 ngày tới.
    - Nếu lặp: Cắt chuỗi lặp (xóa sự kiện này và tương lai).
    - Nếu đơn: Xóa sự kiện này.
    
    Returns:
        tuple: (success: bool, message: str)
    """
    print(f"--- Bắt đầu tìm và xóa chuỗi sự kiện: '{class_name}' ---")
    
    try:
        service = authenticate_google_calendar()
        
        # 1. Thiết lập thời gian quét (0 -> 14 ngày)
        now = datetime.datetime.utcnow()
        time_min = now.isoformat() + 'Z'
        time_max = (now + datetime.timedelta(days=14)).isoformat() + 'Z'

        # 2. Tìm các sự kiện (singleEvents=True để bung các sự kiện lặp ra)
        events_result = service.events().list(
            calendarId=Calendar_ID,
            timeMin=time_min,
            timeMax=time_max,
            q=class_name, # Tìm sơ bộ
            singleEvents=True,
            orderBy='startTime'
        ).execute()

        events = events_result.get('items', [])
        
        if not events:
            msg = f"Không tìm thấy sự kiện nào chứa từ khóa '{class_name}' trong 14 ngày tới."
            return False, msg

        processed_count = 0
        processed_master_ids = set() # Tránh xử lý trùng 1 chuỗi nhiều lần

        for event in events:
            # Kiểm tra tên chính xác (Case-insensitive)
            if event.get('summary', '').strip().lower() != class_name.strip().lower():
                continue
            
            # --- TRƯỜNG HỢP 1: Sự kiện lặp lại (Có recurringEventId) ---
            if 'recurringEventId' in event:
                master_id = event['recurringEventId']
                
                if master_id in processed_master_ids:
                    continue

                try:
                    # Lấy thông tin thời gian
                    is_all_day = 'date' in event['start']
                    start_str = event['start'].get('dateTime') or event['start'].get('date')
                    start_dt = parser.parse(start_str)
                    
                    # Chuyển về UTC
                    start_dt_utc = start_dt.astimezone(datetime.timezone.utc)
                    
                    # --- SỬA LỖI TẠI ĐÂY ---
                    if is_all_day:
                        # Nếu là sự kiện cả ngày: Lùi hẳn 1 ngày + 1 giây để an toàn tuyệt đối với mọi múi giờ
                        # Ví dụ: Sự kiện ngày 25, ta set UNTIL là hết ngày 23.
                        until_dt = start_dt_utc - datetime.timedelta(days=1, seconds=1)
                    else:
                        # Nếu là sự kiện có giờ cụ thể: Chỉ cần trừ 1 giây
                        until_dt = start_dt_utc - datetime.timedelta(seconds=1)
                    
                    until_str = until_dt.strftime('%Y%m%dT%H%M%SZ')
                    # -----------------------

                    # Lấy Master Event gốc
                    master_event = service.events().get(calendarId=Calendar_ID, eventId=master_id).execute()
                    
                    # Sửa RRULE
                    recurrence_rules = master_event.get('recurrence', [])
                    new_recurrence = []
                    if recurrence_rules:
                        for rule in recurrence_rules:
                            if rule.startswith('RRULE:'):
                                rule = re.sub(r';?UNTIL=[^;]+', '', rule)
                                rule = re.sub(r';?COUNT=[^;]+', '', rule)
                                rule += f";UNTIL={until_str}"
                            new_recurrence.append(rule)
                        
                        master_event['recurrence'] = new_recurrence
                        
                        # Cập nhật lên Google
                        service.events().update(
                            calendarId=Calendar_ID, 
                            eventId=master_id, 
                            body=master_event
                        ).execute()

                        processed_master_ids.add(master_id)
                        count_stopped_series += 1

                except Exception as ex:
                    print(f"Lỗi: {ex}")

            # --- TRƯỜNG HỢP 2: Sự kiện đơn lẻ (Không lặp) ---
            else:
                service.events().delete(calendarId=Calendar_ID, eventId=event['id']).execute()
                processed_count += 1

        # KẾT QUẢ TRẢ VỀ
        if processed_count > 0:
            msg = f"Thành công! Đã xóa/ngừng lặp {processed_count} chuỗi sự kiện '{class_name}'."
            return True, msg
        else:
            msg = f"Tìm thấy sự kiện gần giống nhưng không khớp chính xác tên '{class_name}'."
            return False, msg

    except Exception as e:
        error_msg = f"Lỗi hệ thống khi xóa sự kiện: {str(e)}"
        print(error_msg)
        return False, error_msg

# --- HÀM XÁC THỰC (giữ nguyên) ---
def authenticate_google_calendar():
    # ... code không đổi ...
    creds = None; token_path = 'backend/calendar_scanner/token.json'; creds_path = 'backend/calendar_scanner/credentials.json'
    if os.path.exists(token_path): creds = Credentials.from_authorized_user_file(token_path, SCOPES)
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token: creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file(creds_path, SCOPES)
            creds = flow.run_local_server(port=0)
        with open(token_path, 'w') as token: token.write(creds.to_json())
    return build('calendar', 'v3', credentials=creds)

# --- HÀM TIỆN ÍCH ---
def get_teacher_calendars_from_db():
    """
    Đọc file database.json và trả về một dictionary
    có key là Tên giáo viên và value là Calendar ID của họ.
    """
    teacher_calendars = {}
    db_file_path = os.path.join(os.path.dirname(__file__), '..','..', 'database', 'database.json')
    
    try:
        if os.path.exists(db_file_path):
            with open(db_file_path, 'r', encoding='utf-8') as f:
                db_data = json.load(f)
            
            for teacher_name, teacher_info in db_data.items():
                calendar_id = teacher_info.get("ID_Calendar")
                if calendar_id:
                    teacher_calendars[teacher_name] = calendar_id
    except Exception as e:
        print(f"Cảnh báo: Không thể đọc hoặc phân tích database.json. Lỗi: {e}")
    return teacher_calendars

def parse_bill_event_title(title):
    match = re.search(r'Bill\s+(.+)', title.strip(), re.IGNORECASE)
    return match.group(1).strip() if match else None

def parse_session_event_title(title):
    match = re.search(r'(?:K(\d+)B(\d+)|B(\d+)K(\d+))\s+(.+)', title.strip(), re.IGNORECASE)
    if match:
        course_num = int(match.group(1) or match.group(4))
        session_num = int(match.group(2) or match.group(3))
        student_name = match.group(5).strip()
        return student_name, course_num, session_num
    return None, None, None

def format_date_for_bill(dt_object):
    return f"{dt_object.day} tháng {dt_object.month}, {dt_object.year}"


# Số buổi mỗi khóa theo hậu tố tên lớp, khớp quy ước gắn nhãn buổi học trên
# Google Calendar (Apps Script UpdateClass). None = lớp mặc định.
KHOA_SCHEDULES = [
    (re.compile(r'HSK1\s*3\.0\s*$', re.IGNORECASE), [10, 10, 8]),  # tổng 28 buổi / 3 khóa
    (re.compile(r'HSK2\s*3\.0\s*$', re.IGNORECASE), [11, 11]),     # tổng 22 buổi / 2 khóa
]
DEFAULT_KHOA_SIZE = 8  # Lớp không khớp cấu hình trên: 8 buổi/khóa, lặp vô hạn


def get_khoa_sizes(title):
    for pattern, sizes in KHOA_SCHEDULES:
        if pattern.search(title):
            return sizes
    return None


def get_expected_session_count(title, course_num):
    """Số buổi để khóa `course_num` của lớp `title` được coi là hoàn thành."""
    khoa_sizes = get_khoa_sizes(title)
    if khoa_sizes:
        idx = min(course_num, len(khoa_sizes)) - 1
        return khoa_sizes[idx]
    return DEFAULT_KHOA_SIZE


CALENDAR_IDS = get_teacher_calendars_from_db()
REV_CALENDAR_IDS = dict(zip(CALENDAR_IDS.values(), CALENDAR_IDS.keys()))
# --- HÀM CHÍNH ---


def main():
    print("Bắt đầu quét Google Calendar (Chế độ tuần tự)...")
    try:
        service = authenticate_google_calendar()

        # --- GIAI ĐOẠN 1: Tải dữ liệu Recent (Gần đây) ---
        now_utc = datetime.datetime.utcnow()
        time_max_utc = (now_utc + datetime.timedelta(days=1))
        time_max = time_max_utc.isoformat() + 'Z'
        time_min_bill = (now_utc - relativedelta(days=SCAN_RANGE_DAYS)).isoformat() + 'Z'
        time_min_courses = (now_utc - relativedelta(days=SCAN_RANGE_COURSE_DAYS)).isoformat() + 'Z'

        all_recent_events = []
        print(f"Đang tải sự kiện gần đây (trong {SCAN_RANGE_DAYS} ngày)...")
        for key in CALENDAR_IDS:
            try:
                events_result = service.events().list(
                    calendarId=CALENDAR_IDS[key], timeMin=time_min_bill, timeMax=time_max,
                    maxResults=2500, singleEvents=True, orderBy='startTime'
                ).execute()
                all_recent_events.extend(events_result.get('items', []))
            except HttpError: pass

        # --- GIAI ĐOẠN 2: Lọc ra danh sách Bill cần xử lý ---
        bill_tasks = []
        for event in all_recent_events:
            # Logic nhận diện sự kiện Bill
            if 'date' in event['start'] and 'dateTime' not in event['start'] and 'Bill' in event.get('summary', ''):
                student_name = parse_bill_event_title(event.get('summary', ''))
                if student_name:
                    bill_tasks.append({
                        'event': event, 
                        'student_name': student_name, 
                        'teacher': REV_CALENDAR_IDS.get(event.get('organizer', {}).get('email'))
                    })
        
        if not bill_tasks:
            print("Không tìm thấy sự kiện 'Bill'. Kết thúc.")
            return

        # --- GIAI ĐOẠN 3: Tải dữ liệu Lịch sử (Dùng chung) ---
        print("Đang tải toàn bộ dữ liệu lịch sử để tra cứu...")
        all_historical_events = []
        for key in CALENDAR_IDS:
             try:
                events_result = service.events().list(
                    calendarId=CALENDAR_IDS[key], timeMin=time_min_courses, maxResults=2500, singleEvents=True,
                    orderBy='startTime', timeMax=time_max
                ).execute()
                all_historical_events.extend(events_result.get('items', []))
             except HttpError: pass
        
        # Sắp xếp lịch sử theo thời gian để xử lý logic tìm kiếm
        all_historical_events.sort(key=lambda x: x['start'].get('date') or x['start'].get('dateTime'))
        
        # --- GIAI ĐOẠN 4: Xử lý từng Bill (Tuần tự) ---
        student_bill_data = {}
        print(f"\n🚀 Bắt đầu xử lý {len(bill_tasks)} Bills...")

        for task in bill_tasks:
            # Trích xuất thông tin cơ bản
            teacher = task['teacher']
            bill_event = task['event']
            student_name_from_bill = task['student_name']
            bill_date = parse(bill_event['start']['date']).date()

            print(f">> Đang xử lý Bill: {student_name_from_bill} (Ngày {bill_date})...")

            # 4.1: Tìm buổi học cuối cùng của khóa (theo số buổi/khóa của loại lớp) cùng ngày với Bill
            target_course_num = None
            for event in all_recent_events:
                if 'dateTime' in event['start']:
                    evt_date = parse(event['start']['dateTime']).date()
                    if evt_date == bill_date:
                        evt_student, evt_course, evt_session = parse_session_event_title(event.get('summary', ''))
                        if (evt_student and evt_student.lower() == student_name_from_bill.lower() and
                            evt_course is not None and
                            evt_session == get_expected_session_count(student_name_from_bill, evt_course)):
                            target_course_num = evt_course
                            break

            if not target_course_num:
                print(f"   ⚠️ Không tìm thấy buổi kết thúc khóa cùng ngày. Bỏ qua.")
                continue # Chuyển sang Bill tiếp theo

            # 4.2: Tìm mốc ngày bắt đầu thu thập
            previous_course_num = target_course_num - 1
            start_date_to_collect = datetime.date.min 
            inclusive_start = False 

            if previous_course_num > 0:
                # Logic K > 1: Tìm kết thúc khóa trước
                for event in reversed(all_historical_events):
                    evt_date_str = event['start'].get('date') or event['start'].get('dateTime').split('T')[0]
                    evt_date = parse(evt_date_str).date()
                    if evt_date >= bill_date: continue
                    
                    evt_student, evt_course, evt_session = parse_session_event_title(event.get('summary', ''))
                    if (evt_student and evt_student.lower() == student_name_from_bill.lower() and
                        evt_course == previous_course_num and
                        evt_session == get_expected_session_count(student_name_from_bill, previous_course_num)):
                        start_date_to_collect = evt_date
                        break
            
            elif target_course_num == 1:
                # Logic K = 1: Tìm B1K1
                scan_limit_date = bill_date - relativedelta(days=60)
                for event in reversed(all_historical_events):
                    evt_date_str = event['start'].get('date') or event['start'].get('dateTime').split('T')[0]
                    evt_date = parse(evt_date_str).date()
                    if evt_date < scan_limit_date: break
                    if evt_date > bill_date: continue

                    evt_student, evt_course, evt_session_num = parse_session_event_title(event.get('summary', ''))
                    if (evt_student and evt_student.lower() == student_name_from_bill.lower() and
                        evt_course == 1 and evt_session_num == 1):
                        start_date_to_collect = evt_date
                        inclusive_start = True
                        break

            # 4.3: Gom các buổi học vào danh sách
            course_sessions = {'teacher': teacher, 'class':[]}
            
            for event in all_historical_events:
                evt_date_str = event['start'].get('date') or event['start'].get('dateTime').split('T')[0]
                evt_date = parse(evt_date_str).date()

                date_condition_met = False
                if inclusive_start:
                    if start_date_to_collect <= evt_date <= bill_date: date_condition_met = True
                else:
                    if start_date_to_collect < evt_date <= bill_date: date_condition_met = True
                
                evt_student, evt_course, evt_session_num = parse_session_event_title(event.get('summary', ''))
                if date_condition_met:
                    evt_student, evt_course, evt_session_num = parse_session_event_title(event.get('summary', ''))
                    
                    # Debug riêng cho trường hợp cụ thể (nếu cần)
                    if (evt_student and evt_student.lower() == student_name_from_bill.lower() and evt_course == target_course_num):

                        date_str_formatted = format_date_for_bill(evt_date)
                        session_data = {
                            "result": f"{date_str_formatted}, Không có thời gian, B{evt_session_num}K{evt_course}",
                            "date": date_str_formatted
                        }
                        course_sessions['class'].append(session_data)

            # 4.4: Lưu kết quả vào dict tổng
            if course_sessions['class']:
                # Vì chạy tuần tự, không cần Lock
                student_bill_data[student_name_from_bill] = course_sessions
                # print(f"   ✅ Hoàn tất: {len(course_sessions['class'])} buổi.")
            else:
                print(f"   ❌ Không tìm thấy buổi học nào trong khoảng thời gian xác định.")

        # --- GIAI ĐOẠN 5: Ghi file JSON ---
        print("\nĐang ghi dữ liệu mới vào file bill.json...")
        sorted_student_bill_data = dict(sorted(student_bill_data.items()))
        with open(OUTPUT_BILL_JSON_PATH, 'w', encoding='utf-8') as f:
            json.dump(sorted_student_bill_data, f, ensure_ascii=False, indent=2)
        print(" -> Hoàn tất.")

    except Exception as e:
        print(f'Lỗi chương trình: {e}')


def delete_bill_task(student_name, Calendar_ID, cancel_date):
    """
    Tìm sự kiện "Bill" của học viên vào đúng ngày cancel_date (dd/mm).
    Copy sang lịch lưu trữ (TARGET_CALENDAR_ID) và xóa khỏi lịch chính.
    """
    
    # --- CẤU HÌNH ID LỊCH ĐÍCH (GÁN CỨNG) ---
    # ----------------------------------------

    print(f"Bắt đầu quy trình chuyển đổi tác vụ Bill cho '{student_name}' vào ngày {cancel_date}")
    
    try:
        service = authenticate_google_calendar()

        # 1. Xử lý ngày tháng (Từ "dd/mm" -> timeMin, timeMax chuẩn ISO)
        try:
            day, month = map(int, cancel_date.split('/'))
            current_year = datetime.datetime.now().year
            
            # Tạo mốc thời gian bắt đầu ngày đó (00:00:00)
            start_of_day = datetime.datetime(current_year, month, day)
            
            # Tạo mốc thời gian kết thúc (là 00:00:00 của ngày hôm sau)
            end_of_day = start_of_day + datetime.timedelta(days=1)

            # Chuyển sang format ISO mà Google API yêu cầu
            time_min = start_of_day.isoformat() + 'Z'
            time_max = end_of_day.isoformat() + 'Z'
            
        except ValueError:
            return False, f"Định dạng ngày '{cancel_date}' không hợp lệ. Vui lòng dùng dd/mm."

        event_to_move = None

        # 2. Tìm kiếm sự kiện trong ĐÚNG ngày đó
        events_result = service.events().list(
            calendarId=Calendar_ID, 
            timeMin=time_min, 
            timeMax=time_max,
            q=f"Bill {student_name}", # Lọc sơ bộ bằng từ khóa
            singleEvents=True
        ).execute()
        
        # 3. Duyệt và xác thực kỹ sự kiện
        for event in events_result.get('items', []):
            summary = event.get('summary', '')
            
            # Kiểm tra tên học viên (dùng hàm parse cũ của bạn hoặc check in string)
            # Ở đây tôi giữ logic cũ của bạn là dùng parse_bill_event_title
            parsed_name = parse_bill_event_title(summary)
            
            # Điều kiện: 
            # A. Phải là sự kiện cả ngày ('date' in start)
            # B. Tên học viên khớp
            if 'date' in event['start'] and parsed_name and parsed_name.lower() == student_name.lower():
                event_to_move = event
                break
        
        if event_to_move:
            # 4. THỰC HIỆN "DI CHUYỂN"
            
            # Bước 4a: Tạo body cho sự kiện mới (Copy thông tin quan trọng)
            new_event_body = {
                'summary': event_to_move['summary'],
                'start': event_to_move['start'], # Giữ nguyên ngày ('date': 'YYYY-MM-DD')
                'end': event_to_move['end'],
                'description': event_to_move.get('description', '') + "\n(Đã chuyển từ lịch chính)"
            }

            # Bước 4b: Thêm vào lịch đích (TARGET_CALENDAR_ID)
            service.events().insert(calendarId=TARGET_CALENDAR_ID, body=new_event_body).execute()
            print(f" -> Đã sao chép sự kiện sang lịch đích ({TARGET_CALENDAR_ID})")

            # Bước 4c: Xóa khỏi lịch nguồn (Calendar_ID)
            service.events().delete(calendarId=Calendar_ID, eventId=event_to_move['id']).execute()
            
            message = f"Đã chuyển thành công sự kiện '{event_to_move['summary']}' ngày {cancel_date}."
            print(f" -> {message}")
            return True, message

        else:
            message = f"Không tìm thấy Bill '{student_name}' (All-day) vào đúng ngày {cancel_date}."
            print(f" -> {message}")
            return False, message

    except Exception as e:
        error_message = f"Lỗi server khi xử lý sự kiện: {e}"
        print(f" -> {error_message}")
        return False, error_message


def find_specific_class(class_name, course_number, teacher_name=None):
    """
    Tìm kiếm các buổi học của một lớp và khóa cụ thể trên Google Calendar
    với các logic kiểm tra nâng cao.
    """
    print(f"Bắt đầu tìm kiếm: Lớp '{class_name}', Khóa {course_number}")
    try:
        service = authenticate_google_calendar()
        
        # --- LOGIC MỚI: GIỚI HẠN THỜI GIAN QUÉT ---
        now_utc = datetime.datetime.utcnow()
        # Quét từ 90 ngày trước cho đến hiện tại
        time_min = (now_utc - relativedelta(days=90)).isoformat() + 'Z'
        time_max = (now_utc + datetime.timedelta(days=1)).isoformat() + 'Z'

        # --- Bước 1: Quét tất cả sự kiện của học viên trong 90 ngày qua ---
        all_student_events = []
        search_query_student = f'"{class_name}"' # Đặt trong ngoặc kép để tìm chính xác cụm từ

        for calendar_id in CALENDAR_IDS:
            try:
                events_result = service.events().list(
                    calendarId=calendar_id,
                    q=search_query_student,
                    timeMin=time_min,
                    timeMax=time_max,
                    maxResults=100,
                    singleEvents=True,
                    orderBy='startTime'
                ).execute()
                all_student_events.extend(events_result.get('items', []))
            except HttpError as e:
                print(f"  - Cảnh báo: Lỗi khi quét trên calendar '{calendar_id[:20]}...'.")

        if not all_student_events:
            print(" -> Không tìm thấy sự kiện nào của học viên này trong 90 ngày qua.")
            return {}

        # --- Bước 2: Tìm khóa học mới nhất của học viên này ---
        latest_course_found = 0
        for event in all_student_events:
            summary = event.get('summary', '')
            evt_student, evt_course, _ = parse_session_event_title(summary)
            if evt_student and evt_student.lower() == class_name.lower():
                if evt_course > latest_course_found:
                    latest_course_found = evt_course

        print(f" -> Khóa học mới nhất của '{class_name}' tìm thấy trong 90 ngày qua là: K{latest_course_found}")
        # --- Bước 3: Kiểm tra tính hợp lệ của yêu cầu ---
        requested_course_num = int(course_number)
        if requested_course_num > latest_course_found:
            print(f" -> Yêu cầu tìm K{requested_course_num} lớn hơn khóa mới nhất (K{latest_course_found}). Trả về rỗng.")
            # Trả về một dictionary đặc biệt để frontend có thể hiển thị thông báo
            return {"error": f"Học viên này chưa học đến Khóa {requested_course_num}. Khóa mới nhất là {latest_course_found}."}

        # --- Bước 4: Nếu hợp lệ, gom các buổi học của khóa được yêu cầu ---
        print("Hello0")
        found_sessions = []
        for event in all_student_events:
            summary = event.get('summary', '')
            evt_student, evt_course, evt_session_num = parse_session_event_title(summary)
            if (evt_student and evt_student.lower() == class_name.lower() and
                evt_course == requested_course_num):
                
                evt_date = parse(event['start'].get('date') or event['start'].get('dateTime').split('T')[0]).date()
                date_str_formatted = format_date_for_bill(evt_date)
                
                session_data = {
                    "result": f"{date_str_formatted}, Không có thời gian, B{evt_session_num}K{evt_course}",
                    "date": date_str_formatted
                }
                found_sessions.append(session_data)
        found_sessions.sort(key=lambda x: parse(x['date'].replace('tháng ', '')))
        if found_sessions:

            result_data = {class_name: found_sessions}

            print(f" -> Tìm thấy {len(found_sessions)} buổi học cho K{requested_course_num}. Trả về kết quả.")

            return result_data
        else:
            print(f" -> Không tìm thấy buổi học nào cho K{requested_course_num}.")
            return {}

    except Exception as e:
        print(f"Lỗi không xác định trong quá trình tìm kiếm: {e}")
        return {"error": "Lỗi server khi đang tìm kiếm."}


def parse_schedule_string(schedule_str):
    """
    Phân tích chuỗi "Thứ 2, 10:00 - 11:30" thành (day_code, start_time, end_time)
    """
    schedule_parts = []
    if not schedule_str:
        return schedule_parts
        
    day_mapping_reverse = {
        "Thứ 2": "2", "Thứ 3": "3", "Thứ 4": "4", 
        "Thứ 5": "5", "Thứ 6": "6", "Thứ 7": "7", "Chủ Nhật": "CN"
    }
    
    parts = schedule_str.split('|')
    for part in parts:
        part = part.strip()
        try:
            day_text, time_range = part.split(',')
            day_text = day_text.strip()
            day_code = day_mapping_reverse.get(day_text)
            
            start_str, end_str = [t.strip() for t in time_range.split('-')]
            start_time = dt_parse(start_str).time()
            end_time = dt_parse(end_str).time()
            
    
            if day_code:
                schedule_parts.append({
                    "day": day_code,
                    "start": start_time,
                    "end": end_time
                })
        except Exception as e:
            print(f"Cảnh báo: Không thể phân tích lịch học '{part}'. Lỗi: {e}")
            continue
            
    return schedule_parts

def check_schedule_overlap(schedule_a, schedule_b):
    """Kiểm tra xem hai khung giờ có chồng chéo không."""
    # (start1 < end2) and (end1 > start2)
    return schedule_a['start'] < schedule_b['end'] and schedule_a['end'] > schedule_b['start']


def create_calendar_events_for_class(calendar_id, teacher_name, class_name, start_date_str, schedule_str):
    """
    Hàm riêng biệt để tạo chuỗi sự kiện lặp lại trên Google Calendar.
    
    Args:
        calendar_id (str): ID lịch của giáo viên.
        teacher_name (str): Tên giáo viên (để tạo initials).
        class_name (str): Tên lớp học gốc.
        start_date_str (str): Ngày bắt đầu (dd/mm/yyyy).
        schedule_str (str): Chuỗi lịch học (vd: "2: 19:30-21:00, 5: 19:30-21:00").
        
    Returns:
        tuple: (success, message)
    """
    print(f" -> Đang tạo sự kiện Calendar cho lớp '{class_name}'...")
    try:
        service = authenticate_google_calendar()
        
        # 1. Chuẩn bị dữ liệu định danh
        event_summary = f'{class_name}'
        
        # 2. Xử lý thời gian
        tz_info = datetime.timezone(datetime.timedelta(hours=7)) # Múi giờ +07:00
        start_date = dt_parse(start_date_str).date()
        
        # Parse lịch học và sắp xếp theo thứ tự trong tuần
        schedule_list = parse_schedule_string(schedule_str)
        if not schedule_list:
            return False, "Chuỗi lịch học không hợp lệ hoặc rỗng."
            
        schedule_list = sorted(schedule_list, key=lambda s: (DAY_TO_ISOWEEKDAY[s['day']], s['start']))

        # 3. Duyệt qua từng buổi trong tuần để tạo RRULE
        created_count = 0
        for schedule in schedule_list:
            day_code = schedule['day']
            day_rrule = DAY_MAP.get(day_code)
            
            if not day_rrule:
                continue

            # Tính ngày diễn ra buổi học ĐẦU TIÊN của thứ đó kể từ ngày bắt đầu
            first_session_date = start_date
            while DAY_TO_ISOWEEKDAY[day_code] != first_session_date.isoweekday():
                first_session_date += datetime.timedelta(days=1)
            
            # Kết hợp ngày + giờ
            start_datetime = datetime.datetime.combine(first_session_date, schedule["start"], tzinfo=tz_info)
            end_datetime = datetime.datetime.combine(first_session_date, schedule["end"], tzinfo=tz_info)

            # Tạo body sự kiện
            event_body = {
                'summary': event_summary,
                'description': f"Lớp: {class_name}\nGV: {teacher_name}",
                'start': {
                    'dateTime': start_datetime.isoformat(),
                    'timeZone': 'Asia/Ho_Chi_Minh',
                },
                'end': {
                    'dateTime': end_datetime.isoformat(),
                    'timeZone': 'Asia/Ho_Chi_Minh',
                },
                'recurrence': [f'RRULE:FREQ=WEEKLY;BYDAY={day_rrule}'],
            }

            service.events().insert(calendarId=calendar_id, body=event_body).execute()
            print(f"   -> Đã tạo event lặp lại vào thứ {day_code}: {event_summary}")
            created_count += 1
            
        return True, f"Đã tạo {created_count} chuỗi sự kiện trên lịch."

    except Exception as e:
        return False, f"Lỗi Google Calendar API: {e}"


def create_new_class(teacher_name, class_name, class_details, session_control):
    """Hàm xử lý logic chính cho việc thêm lớp mới."""
    print(f"Bắt đầu quy trình thêm lớp: GV '{teacher_name}', Lớp '{class_name}'")
    
    # Tạo Key chuẩn cho Database (dùng chung cho cả lúc lưu và lúc xóa rollback)
    teacher_initials = "".join(word[0] for word in teacher_name.split()).upper()
    db_class_key = f"Rucao_{teacher_initials}_{class_name}"

    try:
        # --- 1. KIỂM TRA DỮ LIỆU & DATABASE ---
        db_data = {}
        if os.path.exists(DATA_BASE_PATH):
            with open(DATA_BASE_PATH, 'r', encoding='utf-8') as f:
                db_data = json.load(f)
        
        teacher_info = db_data.get(teacher_name)
        if not teacher_info or 'ID_Calendar' not in teacher_info or not teacher_info['ID_Calendar']:
            return False, {"error": f"Không tìm thấy Calendar ID hợp lệ cho giáo viên {teacher_name}."}
        calendar_id = teacher_info['ID_Calendar']

        # --- 2. KIỂM TRA TRÙNG LỊCH ---
        print(" -> Kiểm tra trùng lịch...")
        new_class_schedule_str = class_details.get('Study_week_day', '')
        new_class_schedule_list = parse_schedule_string(new_class_schedule_str)
        
        if new_class_schedule_list:
            active_classes = [
                cls_details for cls_key, cls_details in db_data.get(teacher_name, {}).get("Class", {}).items()
                if cls_details.get("isActive") == "True" and cls_key != db_class_key
            ]

            for new_item in new_class_schedule_list:
                new_day_code = new_item['day']
                for active_class in active_classes:
                    existing_list = parse_schedule_string(active_class.get('Study_week_day', ''))
                    for existing_item in existing_list:
                        if existing_item['day'] == new_day_code:
                            if check_schedule_overlap(new_item, existing_item):
                                day_text = {"2":"Thứ 2", "3":"Thứ 3", "4":"Thứ 4", "5":"Thứ 5", "6":"Thứ 6", "7":"Thứ 7", "CN":"CN"}.get(new_day_code, new_day_code)
                                # Tìm tên lớp bị trùng để báo lỗi
                                conflict_name = next((k for k, v in db_data[teacher_name]["Class"].items() if v == active_class), "Unknown")
                                return False, {"error": f"Trùng lịch vào {day_text} lúc {new_item['start'].strftime('%H:%M')} với lớp '{conflict_name}'."}
        
        print(" -> Không có lịch trùng.")

        # --- 3. LƯU VÀO DATABASE ---
        if "Class" not in db_data[teacher_name]: 
            db_data[teacher_name]["Class"] = {}
            
        # Lưu với key chuẩn đã tạo ở đầu hàm
        db_data[teacher_name]["Class"][db_class_key] = class_details
        
        with open(DATA_BASE_PATH, 'w', encoding='utf-8') as f:
            json.dump(db_data, f, ensure_ascii=False, indent=2)

        # --- 4. GỌI HÀM TẠO CALENDAR (Đã tách riêng) ---
       
        if session_control:
            cal_success, cal_msg = create_calendar_events_for_class(
                calendar_id=calendar_id,
                teacher_name=teacher_name,
                class_name=db_class_key,
                start_date_str=class_details['ngayBatDau'],
                schedule_str=class_details.get('Study_week_day')
            )
            


            if not cal_success:
                # Nếu tạo lịch thất bại -> Có thể raise lỗi để nhảy xuống rollback
                raise Exception(f"Lỗi tạo Calendar: {cal_msg}")
        else:
            print(" -> Bỏ qua tạo sự kiện (Kiểm soát buổi: Tắt).")

        return True, {"message": "Thêm lớp và tạo lịch thành công!", "newData": db_data}

    except Exception as e:
        # --- 5. ROLLBACK (Xóa data nếu lỗi) ---
        print(f"Lỗi nghiêm trọng: {e}. Đang thử rollback...")
        # Load lại DB mới nhất để đảm bảo xóa đúng
        try:
            if os.path.exists(DATA_BASE_PATH):
                with open(DATA_BASE_PATH, 'r', encoding='utf-8') as f:
                    current_db = json.load(f)
                
                # Kiểm tra và xóa đúng key đã tạo
                if teacher_name in current_db and "Class" in current_db[teacher_name]:
                    if db_class_key in current_db[teacher_name]["Class"]:
                        del current_db[teacher_name]["Class"][db_class_key]
                        with open(DATA_BASE_PATH, 'w', encoding='utf-8') as f:
                            json.dump(current_db, f, ensure_ascii=False, indent=2)
                        print(f" -> Rollback thành công: Đã xóa '{db_class_key}' khỏi DB.")
        except Exception as rb_e:
            print(f" -> Rollback thất bại: {rb_e}")
            
        return False, {"error": f"Lỗi server: {e}"}