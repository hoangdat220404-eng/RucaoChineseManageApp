/**
 * Tên file: Logic_bill_cal.js
 * Chức năng: Xử lý logic cho trang tính bill của RucaoChinese.
 * Bao gồm:
 *  - Tải dữ liệu mặc định từ server hoặc xử lý file do người dùng tải lên.
 *  - Lọc, sắp xếp và hiển thị danh sách học viên đủ điều kiện.
 *  - Vẽ thông tin bill lên ảnh mẫu (template).
 *  - Cung cấp chức năng Tải ảnh về hoặc Copy ảnh vào clipboard.
 */

// --- 1. KHAI BÁO BIẾN & LẤY CÁC PHẦN TỬ DOM ---
// const jsonInput = document.getElementById('json-input');
const jsonInput = document.getElementById('json-input');
const dropZone = document.getElementById('drop-zone');
const fileNameDisplay = document.getElementById('file-name-display');

const studentSelect = document.getElementById('student-select');
const studentSelectorDiv = document.getElementById('student-selector-div');
const actionButtonsGroup = document.getElementById('action-buttons-group');
const canvas = document.getElementById('certificateCanvas');
const ctx = canvas.getContext('2d');
const mainContainer = document.querySelector('.container');

// Nút bấm
const generateBtn = document.getElementById('generate-btn');
const copyBtn = document.getElementById('copy-btn');
const cancelBillBtn = document.getElementById('cancel-bill-btn');
const refreshBtn = document.getElementById('refresh-btn');

// Các phần tử của card tìm kiếm
const searchCard = document.getElementById('search-card');
const closeSearchBtn = document.getElementById('close-search-btn');
const findTeacherSelect = document.getElementById('find-teacher');
const findStudentSelect = document.getElementById('find-student');
const findCourseSelect = document.getElementById('find-course');
const findDatesBtn = document.getElementById('find-dates-btn');


// Biến toàn cục
let allData = null; // Sẽ chứa dữ liệu thô (từ server hoặc file)
let assetsReady = false; // Cờ báo hiệu ảnh và font đã sẵn sàng

// Đối tượng ảnh mẫu
const templateImage = new Image();
const templateImage12b = new Image();


// --- 2. CÁC HÀM XỬ LÝ DỮ LIỆU VÀ GIAO DIỆN ---

/**
 * Xử lý dữ liệu thô, lọc, sắp xếp và hiển thị danh sách học viên lên dropdown.
 * Đây là "bộ não" logic nghiệp vụ chính ở frontend.
 */

function exportDataForSave () {
    console.log("🐍 Python đang lấy dữ liệu!");
    
    // 1. Gom dữ liệu
    // Lưu ý: Đảm bảo teacherClassData có thể truy cập được (scope)
    // Nếu biến nằm trong Vue/React, bạn cần truy xuất đúng cách.
    var dataToSend = teacherClassData ; 
    
    // 2. TRẢ VỀ DỮ LIỆU TRỰC TIẾP (QUAN TRỌNG)
    return JSON.stringify(dataToSend); 
}


function formatDate(dateString) {
    const parts = dateString.replace(',', '').split(' ');
    if (parts.length < 3) return dateString;
    const day = parts[0].padStart(2, '0');
    const monthMap = { "1": "01", "2": "02", "3": "03", "4": "04", "5": "05", "6": "06", "7": "07", "8": "08", "9": "09", "10": "10", "11": "11", "12": "12" };
    const monthNumber = monthMap[parts[2]] || parts[2].padStart(2, '0');
    return `${day}/${monthNumber}`;
}


function processAndDisplayBillData(Process_Data) {
    studentSelect.innerHTML = '';
    const studentNames = Object.keys(Process_Data);

    const validOptions = [];
    const disabledOptions = [];

    if (studentNames.length === 0) {
        studentSelectorDiv.style.display = 'none';
        actionButtonsGroup.style.display = 'none';
        alert("Thông báo: Không có dữ liệu học viên nào để hiển thị.");
        return;
    }
    
    studentSelectorDiv.style.display = 'block';
    for (const studentName of studentNames) {
        const sessions = Process_Data[studentName];
        const option = document.createElement('option');

        // Server đã tính sẵn số buổi kỳ vọng theo loại lớp (HSK1 3.0, HSK2 3.0, lớp thường)
        // và trả về isDisabled, nên không tính lại ở đây.
        if (!sessions.isDisabled) {
            const dates = sessions.dates.map(s => formatDate(s));
            option.value = `${sessions.name}|${sessions.courseNumber}`;
            option.textContent = `${sessions.displayText}`;
            option.dataset.dates = JSON.stringify(dates);
            validOptions.push(option);
        } else {
            option.disabled = true;
            option.textContent = `${sessions.displayText}`;
            disabledOptions.push(option);
        }
    }
    validOptions.sort((a, b) => a.textContent.localeCompare(b.textContent));
    disabledOptions.sort((a, b) => a.textContent.localeCompare(b.textContent));
    studentSelect.append(...validOptions, ...disabledOptions);
    if (validOptions.length === 0) {
        option = document.createElement('option')
        option.disabled = true;
        option.textContent = "--- Không còn bill hợp lệ ---"
        studentSelect.append(option);
        actionButtonsGroup.style.display = 'flex';
    } else {
        actionButtonsGroup.style.display = 'flex';
    }
}


function processAndDisplayData() {
    studentSelect.innerHTML = '';
    const studentNames = Object.keys(allData);

    const validOptions = [];
    const disabledOptions = [];

    if (studentNames.length === 0) {
        studentSelectorDiv.style.display = 'none';
        actionButtonsGroup.style.display = 'none';
        return;
    }
    
    studentSelectorDiv.style.display = 'block';
    for (const studentName of studentNames) {
        const sessions = allData[studentName];
        const option = document.createElement('option');

        // Server đã tính sẵn số buổi kỳ vọng theo loại lớp (HSK1 3.0, HSK2 3.0, lớp thường)
        // và trả về isDisabled, nên không tính lại ở đây.
        if (!sessions.isDisabled) {
            const dates = sessions.dates.map(s => formatDate(s));
            option.value = `${sessions.name}|${sessions.courseNumber}`;
            option.textContent = `${sessions.displayText}`;
            option.dataset.dates = JSON.stringify(dates);
            option.dataset.teacher = sessions.teacher;
            validOptions.push(option);
        } else {
            option.disabled = true;
            option.textContent = `${sessions.displayText}`;
            disabledOptions.push(option);
        }
    }
    validOptions.sort((a, b) => a.textContent.localeCompare(b.textContent));
    disabledOptions.sort((a, b) => a.textContent.localeCompare(b.textContent));
    studentSelect.append(...validOptions, ...disabledOptions);
    if (validOptions.length === 0) {
        option = document.createElement('option')
        option.textContent =  "--- Không còn bill hợp lệ ---";
        studentSelect.append(option);

        actionButtonsGroup.style.display = 'flex';
    } else {
        actionButtonsGroup.style.display = 'flex';
    }
}


function populateSearchFilters() {
    if (!teacherClassData) return;

    // 1. Điền danh sách giáo viên
    const teachers = Object.keys(teacherClassData).sort();
    console.log("Hello");
    console.log(teachers);
    populateSelect(findTeacherSelect, teachers, "--- Chọn giáo viên ---");

    // 2. Reset và thiết lập sự kiện cho dropdown lớp học/học viên
    populateSelect(findStudentSelect, [], "--- Chọn giáo viên trước ---");
    findStudentSelect.disabled = true;

    // 3. Điền các khóa từ 1-10
    const courseNumbers = Array.from({length: 10}, (_, i) => i + 1);
    populateSelect(findCourseSelect, courseNumbers, "--- Chọn khóa ---");
}

/**
 * Hàm tiện ích để xóa và điền các options mới vào một thẻ <select>.
 * @param {HTMLSelectElement} selectElement - Thẻ <select> cần cập nhật.
 * @param {string[]} dataArray - Mảng các chuỗi để tạo options.
 * @param {string} defaultText - Dòng chữ cho option mặc định (option đầu tiên).
 */
function populateSelect(selectElement, dataArray, defaultText) {
    // Xóa tất cả các option cũ
    selectElement.innerHTML = '';

    // Tạo và thêm option mặc định, không có giá trị
    const defaultOption = document.createElement('option');
    defaultOption.value = '';
    defaultOption.textContent = defaultText;
    selectElement.appendChild(defaultOption);
    console.log(dataArray[0]);
    // Lặp qua mảng dữ liệu và tạo các option khác
    if (dataArray) {
        dataArray.forEach(item => {

            const option = document.createElement('option');
            option.value = item;
            if (defaultText == "--- Chọn giáo viên ---"){
                option.textContent = "Cô " + item;
            }
            else {
                option.textContent = item;
            }
            selectElement.appendChild(option);
        });
    }
}






// --- 3. CÁC HÀM TIỆN ÍCH (Format ngày, Copy, Download) ---



async function copyCanvasToClipboard(canvasElement) {
    // Kiểm tra hỗ trợ
    if (!navigator.clipboard || !navigator.clipboard.write) {
        alert("Trình duyệt không hỗ trợ copy.");
        downloadCanvasAsImage_fallback(canvasElement, "bill_fallback.png");
        return;
    }

    try {
        // --- ĐOẠN SỬA ĐỔI QUAN TRỌNG ---
        // Thay vì await blob bên ngoài, ta ném Promise thẳng vào trong ClipboardItem.
        // Đây là cách Safari/WebKit trên Mac yêu cầu.
        const clipboardItemInput = new ClipboardItem({
            'image/png': new Promise(async (resolve) => {
                canvasElement.toBlob((blob) => {
                    resolve(blob);
                }, 'image/png');
            })
        });
        // --------------------------------

        await navigator.clipboard.write([clipboardItemInput]);
        
        // Hiệu ứng thành công
        if (typeof copyBtn !== 'undefined') { // Kiểm tra lỡ biến copyBtn chưa khai báo
            copyBtn.classList.add('copied');
            setTimeout(() => copyBtn.classList.remove('copied'), 2000);
        }
        console.log("Đã copy ảnh thành công!");

    } catch (error) {
        // IN LỖI RA ĐỂ DEBUG
        console.error("CHI TIẾT LỖI TRÊN MAC:", error); 
        console.error("Tên lỗi:", error.name);
        console.error("Thông điệp:", error.message);

        alert("Không thể copy ảnh (Lỗi: " + error.name + "). Đang tải về...");
        downloadCanvasAsImage_fallback(canvasElement, "bill_error.png");
    }
}

function downloadCanvasAsImage_fallback(canvasElement, fileName) {
     try {
        const link = document.createElement('a');
        link.download = fileName;
        link.href = canvasElement.toDataURL("image/png");
        document.body.appendChild(link);
        link.click();
        document.body.removeChild(link);
    } catch (error) {
        console.error("Lỗi khi tải ảnh:", error);
    }
}

function drawBillOnCanvas(studentName, courseNumber, dates) {
    let selectedTemplate;
    let lineHeight;
    const sessionCount = dates.length;

    // Chưa có template riêng cho khóa 10 buổi (HSK1 3.0) và 11 buổi (HSK2 3.0)
    // -> dùng tạm template 12 buổi, các dòng dư ở cuối để trống.
    if (sessionCount <= 8) {
        selectedTemplate = templateImage;
        lineHeight = 80;
    } else if (sessionCount <= 12) {
        selectedTemplate = templateImage12b;
        lineHeight = 60;
    } else {
        console.error("Số buổi không hợp lệ để vẽ:", sessionCount);
        alert(`Lỗi: Khóa có ${sessionCount} buổi, vượt quá template tối đa 12 buổi.`);
        return null;
    }
    
    canvas.width = selectedTemplate.width;
    canvas.height = selectedTemplate.height;
    ctx.drawImage(selectedTemplate, 0, 0, canvas.width, canvas.height);

    ctx.fillStyle = '#333333';
    ctx.textAlign = 'left';
    ctx.font = 'bold 40px "Nunito"';
    ctx.fillText(studentName.toUpperCase(), 200, 550);
    ctx.font = 'bold 32px "Nunito"';
    ctx.fillText(`TỔNG KẾT KHÓA ${courseNumber}`, 930, 550);
    ctx.font = '35px "Nunito"';
    let startY = 800;
    dates.forEach((date, index) => {
        ctx.fillText(date, 365, startY + (index * lineHeight));
    });
    return canvas;
}
// --- 4. LOGIC KHỞI TẠO VÀ XỬ LÝ SỰ KIỆN ---

/**
 * Tải dữ liệu mặc định từ server và hiển thị.
 */
async function loadBillData() {
    try {
        const url = `/api/get-bill-data?_=${new Date().getTime()}`;
        const response = await fetch(url);
        if (!response.ok) {
            // Nếu lỗi, throw error để khối catch bên ngoài bắt được
            const errData = await response.json().catch(() => ({ error: 'Lỗi không xác định từ server.' }));
            throw new Error(errData.error || 'Lỗi kết nối server.');
        }
        
      

        allData = await response.json();
        console.log(allData);
        processAndDisplayData();

    } catch (error) {
        // Ném lỗi ra ngoài để hàm gọi nó có thể xử lý
        throw error; 
    }
}


async function  loadAndProcessInitDataBill() {
    try {
        allData = JSON.parse(sessionStorage.getItem('BillData'));
        processAndDisplayData();
        console.log(allData)
        setTimeout(() => {
            mainContainer.classList.remove('refreshing');
          }, 700);
        

        if (!allData){
            console.log("Không có dữ liệu Bill toàn cục");
            return 
        } 
    } catch (error) {
        // Ném lỗi ra để hàm gọi nó xử lý (hiển thị alert)
        mainContainer.classList.remove('refreshing');
        throw error;
    }
}



async function initializeApp() {
    studentSelectorDiv.style.display = 'block';
    actionButtonsGroup.style.display = 'flex';
    mainContainer.classList.add('refreshing');
    try {
        // Tải các asset tĩnh
        const image8bPromise = new Promise(resolve => templateImage.onload = resolve);
        const image12bPromise = new Promise(resolve => templateImage12b.onload = resolve);
        templateImage.src = defaultImageData;
        templateImage12b.src = defaultImageData12b;
        
        
        await Promise.all([image8bPromise, image12bPromise, document.fonts.ready, loadAndProcessInitData()]);
        console.log("Tất cả ảnh, font database đã sẵn sàng!");

        
        
        populateSearchFilters();
        // checkScanStatus(true);
        loadAndProcessInitDataBill();
        
        
    } catch (error) {
        console.error("Lỗi khi khởi tạo:", error);
        alert(`Không thể tải dữ liệu khởi tạo.\nLỗi: ${error.message}`);
    } finally {
        // Tắt hiệu ứng loading dù thành công hay thất bại
        //mainContainer.classList.remove('refreshing');
    }
}





async function  loadAndProcessInitData() {
    try {
         
        teacherClassData =    JSON.parse(sessionStorage.getItem('teacherClassDB'));
        if (!teacherClassData){
            console.log("Không có dữ liệu giáo viên toàn cục");
            return 
        }

        
    } catch (error) {
        // Ném lỗi ra để hàm gọi nó xử lý (hiển thị alert)
        throw error;
    }
}

/**
 * Bắt đầu chu trình kiểm tra trạng thái quét của backend.
 * Khi quét xong, nó sẽ tải dữ liệu bill mới nhất.
 * @param {boolean} isInitialLoad - Cờ để biết đây là lần tải đầu tiên hay do người dùng nhấn refresh.
 */
async function checkScanStatus(isInitialLoad = false) {
    const intervalId = setInterval(async () => {
        try {
            // 1. Hỏi backend xem đã quét xong chưa
            const statusRes = await fetch('/api/scan-status');
            if (!statusRes.ok) throw new Error("Mất kết nối server.");
            
            const statusData = await statusRes.json();
            
            // 2. Nếu đã quét xong (is_scanning là false)
            if (!statusData.is_scanning) {
                // Dừng vòng lặp kiểm tra
                clearInterval(intervalId);
                console.log("Backend đã quét xong. Đang tải dữ liệu bill...");

                // 3. Tải dữ liệu bill đã được backend xử lý
                loadBillData(); 

                // 4. Tắt hiệu ứng loading trên giao diện
                mainContainer.classList.remove('refreshing');
                
                // 5. Nếu đây là hành động refresh của người dùng, hiển thị tích xanh
                if (!isInitialLoad) {
                    showSuccessEffect(refreshBtn);
                }
            }
            // Nếu is_scanning vẫn là true, không làm gì cả, đợi lần kiểm tra tiếp theo
        } catch (error) {
            // Dừng vòng lặp nếu có lỗi và thông báo
            clearInterval(intervalId);
            mainContainer.classList.remove('refreshing');
            alert(`Lỗi khi kiểm tra trạng thái server: ${error.message}`);
        }
    }, 3000); // Lặp lại việc kiểm tra mỗi 3 giây
}




/**
 * Xử lý file do người dùng tải lên.
 */
function handleFile(file) {
    fileNameDisplay.textContent = `Đang xử lý: ${file.name}`;
    mainContainer.classList.add('refreshing');
    const reader = new FileReader();
    reader.onload = async (event) => {
        try {
            const rawData = JSON.parse(event.target.result);
            // Gửi dữ liệu thô lên backend để được xử lý
            const response = await fetch('/api/process-custom-data', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(rawData)
            });
            if (!response.ok) throw new Error((await response.json()).error);
            const processedBillData = await response.json();
            console.log(processedBillData);
            processAndDisplayBillData(processedBillData); // Hiển thị kết quả đã được backend xử lý
        } catch (error) {
            alert(`Lỗi xử lý file: ${error.message}`);
        } finally {
            mainContainer.classList.remove('refreshing');
        }
    };
    reader.readAsText(file);
}



function showDeleteConfirmModal(message, onConfirmCallback) {
    // 1. Xóa modal cũ nếu còn tồn tại
    const existingModal = document.getElementById('deleteConfirmModal');
    if (existingModal) existingModal.remove();

    // 2. Tạo HTML cho Modal
    const modalHTML = `
    <div class="warning-modal-overlay" id="deleteConfirmModal">
        <div class="warning-modal-box">
            <!-- Icon Thùng Rác -->
            <svg class="delete-icon-svg" xmlns="http://www.w3.org/2000/svg" fill="currentColor" viewBox="0 0 16 16">
                <path d="M5.5 5.5A.5.5 0 0 1 6 6v6a.5.5 0 0 1-1 0V6a.5.5 0 0 1 .5-.5zm2.5 0a.5.5 0 0 1 .5.5v6a.5.5 0 0 1-1 0V6a.5.5 0 0 1 .5-.5zm3 .5a.5.5 0 0 0-1 0v6a.5.5 0 0 0 1 0V6z"/>
                <path fill-rule="evenodd" d="M14.5 3a1 1 0 0 1-1 1H13v9a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V4h-.5a1 1 0 0 1-1-1V2a1 1 0 0 1 1-1H6a1 1 0 0 1 1-1h2a1 1 0 0 1 1 1h3.5a1 1 0 0 1 1 1v1zM4.118 4 4 4.059V13a1 1 0 0 0 1 1h6a1 1 0 0 0 1-1V4.059L11.882 4H4.118zM2.5 3V2h11v1h-11z"/>
            </svg>
            
            <div class="warning-title">Xác nhận xóa</div>
            <div class="warning-text">
                ${message}
            </div>

            <div class="warning-actions">
                <!-- Nút Hủy (Xám) -->
                <button id="btnCancelDelete" class="btn-circle btn-cancel-gray" title="Hủy bỏ">
                    <svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" fill="currentColor" viewBox="0 0 16 16">
                         <path d="M4.646 4.646a.5.5 0 0 1 .708 0L8 7.293l2.646-2.647a.5.5 0 0 1 .708.708L8.707 8l2.647 2.646a.5.5 0 0 1-.708.708L8 8.707l-2.646 2.647a.5.5 0 0 1-.708-.708L7.293 8 4.646 5.354a.5.5 0 0 1 0-.708z"/>
                    </svg>
                </button>

                <!-- Nút Xóa (Đỏ) -->
                <button id="btnConfirmDelete" class="btn-circle btn-delete-confirm" title="Xóa vĩnh viễn">
                    <svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" fill="currentColor" viewBox="0 0 16 16">
                        <path d="M5.5 5.5A.5.5 0 0 1 6 6v6a.5.5 0 0 1-1 0V6a.5.5 0 0 1 .5-.5zm2.5 0a.5.5 0 0 1 .5.5v6a.5.5 0 0 1-1 0V6a.5.5 0 0 1 .5-.5zm3 .5a.5.5 0 0 0-1 0v6a.5.5 0 0 0 1 0V6z"/>
                        <path fill-rule="evenodd" d="M14.5 3a1 1 0 0 1-1 1H13v9a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V4h-.5a1 1 0 0 1-1-1V2a1 1 0 0 1 1-1H6a1 1 0 0 1 1-1h2a1 1 0 0 1 1 1h3.5a1 1 0 0 1 1 1v1zM4.118 4 4 4.059V13a1 1 0 0 0 1 1h6a1 1 0 0 0 1-1V4.059L11.882 4H4.118zM2.5 3V2h11v1h-11z"/>
                    </svg>
                </button>
            </div>
        </div>
    </div>
    `;

    document.body.insertAdjacentHTML('beforeend', modalHTML);

    // 3. Gán sự kiện
    const modal = document.getElementById('deleteConfirmModal');

    // Nút Hủy
    document.getElementById('btnCancelDelete').onclick = function() {
        modal.remove(); // Đóng modal và không làm gì cả
    };

    // Nút Xác nhận Xóa
    document.getElementById('btnConfirmDelete').onclick = function() {
        modal.remove(); // Đóng modal
        onConfirmCallback(); // CHẠY HÀM XÓA CỦA BẠN
    };
}






// Bắt đầu toàn bộ quá trình khi trang được tải
document.addEventListener('DOMContentLoaded', () => {
    initializeApp();
});

// Event listener cho khu vực kéo-thả file
['dragenter', 'dragover', 'dragleave', 'drop'].forEach(eventName => {
    dropZone.addEventListener(eventName, e => { e.preventDefault(); e.stopPropagation(); }, false);
});
['dragenter', 'dragover'].forEach(eventName => dropZone.addEventListener(eventName, () => dropZone.classList.add('drag-over'), false));
['dragleave', 'drop'].forEach(eventName => dropZone.addEventListener(eventName, () => dropZone.classList.remove('drag-over'), false));

dropZone.addEventListener('drop', (e) => {
    const files = e.dataTransfer.files;
    if (files.length > 0 && (files[0].type === "application/json" || files[0].name.endsWith('.json'))) {
        handleFile(files[0]);
    } else {
        alert("Lỗi: Vui lòng chỉ chọn file có định dạng .json");
    }
}, false);


function showSuccessEffect(buttonElement) {
    buttonElement.classList.add('success');
    setTimeout(() => {
        buttonElement.classList.remove('success');
    }, 500);
}

cancelBillBtn.addEventListener('click', (e) => { // Bỏ async ở đây vì không await gì ở cấp ngoài cùng
    try {
        // --- BƯỚC 1: KIỂM TRA DOM ---
        const selectedOption = studentSelect.options[studentSelect.selectedIndex];
        
        if (!selectedOption || selectedOption.disabled || selectedOption.value === "") {
            alert('Vui lòng chọn một học viên hợp lệ để thực hiện thao tác.');
            return;
        }

        // --- BƯỚC 2: LẤY VÀ KIỂM TRA DỮ LIỆU AN TOÀN ---
        const selectedTeacher = selectedOption.dataset.teacher;
        const listdates = selectedOption.dataset.dates;

        // Kiểm tra biến toàn cục teacherClassData
        if (!teacherClassData || !teacherClassData[selectedTeacher]) {
            alert("Không tìm thấy dữ liệu giáo viên hoặc lớp học.");
            return;
        }
        const ID_calendar = teacherClassData[selectedTeacher]['ID_Calendar'];

        // --- BƯỚC 3: XỬ LÝ JSON AN TOÀN ---
        let lastday = null;
        try {
            if (!listdates) throw new Error("Dữ liệu ngày trống");
            
            // Xử lý chuỗi JSON (Replace an toàn hơn)
            const cleanString = listdates.replace(/&quot;/g, '"');
            const myArray = JSON.parse(cleanString);
            
            if (!Array.isArray(myArray) || myArray.length === 0) {
                alert("Dữ liệu ngày học của học viên này bị lỗi (Rỗng).");
                return;
            }
            
            // Lấy ngày cuối
            lastday = myArray.at(-1); 
            
        } catch (jsonError) {
            console.error("Lỗi parse JSON:", jsonError);
            alert("Lỗi dữ liệu hệ thống (JSON dates). Vui lòng liên hệ kỹ thuật.");
            return; // Dừng lại ngay nếu lỗi dữ liệu
        }

        // --- BƯỚC 4: LẤY TÊN HỌC VIÊN ---
        const studentInfoText = selectedOption.textContent;
        const nameMatch = studentInfoText.match(/(.+) - Khóa/);
        
        // Fallback: Nếu regex không bắt được thì lấy nguyên chuỗi
        const studentName = nameMatch ? nameMatch[1].trim() : studentInfoText.trim();


        // --- BƯỚC 5: HIỆN MODAL ---
        showDeleteConfirmModal(
            `Bạn có chắc chắn muốn xóa tác vụ <strong>"Bill ${studentName}"</strong> trên Google Calendar không?`, 
            
            // Callback Async xử lý xóa
            async function() {
                console.log("Người dùng đã bấm Xóa!");
                
                // Disable nút ngay lập tức để tránh bấm kép
                cancelBillBtn.disabled = true;

                try {
                    const response = await fetch('/api/cancel-bill-task', {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({
                            studentName: studentName, 
                            ID_calendar: ID_calendar,
                            Bill_date: lastday
                        })
                    });

                    const result = await response.json();
                    if (!response.ok) throw new Error(result.error);
                    
                    // Hiệu ứng thành công (Nếu bạn có hàm này)
                    if (typeof showSuccessEffect === 'function') {
                        showSuccessEffect(cancelBillBtn);
                    } else {
                        alert(result.message || "Xóa thành công!");
                    }

                    // Cập nhật giao diện option
                   
                    selectedOption.disabled = true;
                    selectedOption.classList.add('processed');
                    
                    allData.forEach(course=>{
                        console.log(course.displayText);
                        console.log(selectedOption.textContent);
                        if (course.displayText === selectedOption.textContent){
                            course.isDisabled = true; 
                            console.log("hello2")
                        }
                    })
                    console.log(allData);

                    sessionStorage.setItem('BillData', JSON.stringify(allData));
                    // Cập nhật text an toàn
                    if (!selectedOption.textContent.includes("Đã xóa")) {
                        selectedOption.textContent = `${selectedOption.textContent} (Đã xóa Calendar)`;
                    }
                    
                    // Reset select về mặc định (Tuỳ chọn)
                    showSuccessEffect(cancelBillBtn);
                } catch (error) {
                    alert(`Lỗi khi xóa tác vụ: ${error.message}`);
                } finally {
                    // Khôi phục nút bấm sau 2s
                    setTimeout(() => {
                        cancelBillBtn.disabled = false;
                    }, 2000);
                }
            }
        );
       
    } catch (e) {
        console.error("Lỗi không mong muốn:", e);
        alert("Đã xảy ra lỗi cục bộ: " + e.message);
    }
});

// ====> THAY THẾ TOÀN BỘ EVENT LISTENER CỦA NÚT REFRESH BẰNG ĐOẠN NÀY <====
refreshBtn.addEventListener('click', async () => {
    if (mainContainer.classList.contains('refreshing')) return;

    mainContainer.classList.add('refreshing');
    try {
        // Gửi yêu cầu quét lại calendar
        const response = await fetch('/api/refresh-calendar', { method: 'POST' });
        if (!response.ok) throw new Error((await response.json()).message);
        
        console.log((await response.json()).message);

        // Bắt đầu chu trình chờ backend quét xong
        checkScanStatus(false);

    } catch (error) {
        alert(`Lỗi khi yêu cầu làm mới: ${error.message}`);
        mainContainer.classList.remove('refreshing');
    }
});

// Event listener cho nút Tải ảnh
generateBtn.addEventListener('click', () => {
    const selectedOption = studentSelect.options[studentSelect.selectedIndex];
    if (!selectedOption || selectedOption.disabled) { alert('Vui lòng chọn học viên hợp lệ!'); return; }
    
    const [studentName, courseNumber] = selectedOption.value.split('|');
    const dates = JSON.parse(selectedOption.dataset.dates);
    
    const finalCanvas = drawBillOnCanvas(studentName, courseNumber, dates);
    if (finalCanvas) {
        const fileName = `${studentName.replace(/\s+/g, '_')}_Khoa${courseNumber}.png`;
        downloadCanvasAsImage_fallback(finalCanvas, fileName);

    }
});

// Event listener cho nút Copy ảnh
copyBtn.addEventListener('click', () => {
    const selectedOption = studentSelect.options[studentSelect.selectedIndex];
    if (!selectedOption || selectedOption.disabled) { alert('Vui lòng chọn học viên hợp lệ!'); return; }
    
    const [studentName, courseNumber] = selectedOption.value.split('|');
    const dates = JSON.parse(selectedOption.dataset.dates);
    
    const finalCanvas = drawBillOnCanvas(studentName, courseNumber, dates);
    if (finalCanvas) {
        copyCanvasToClipboard(finalCanvas);
    }
    showSuccessEffect(copyBtn); // Thay cho alert

});

searchCard.addEventListener('click', () => {
    // Chỉ kích hoạt nếu chưa ở trạng thái mở rộng
    if (!mainContainer.classList.contains('search-active')) {
        mainContainer.classList.add('search-active');
    }
});

// Đóng (thu nhỏ) lại khi click nút X
closeSearchBtn.addEventListener('click', (event) => {
    event.stopPropagation(); // Ngăn sự kiện click này nổi bọt lên searchCard
    mainContainer.classList.remove('search-active');
});

findTeacherSelect.addEventListener('change', () => {
    const selectedTeacher = findTeacherSelect.value;
    if (selectedTeacher && teacherClassData[selectedTeacher]) {
        const classes = Object.keys(teacherClassData[selectedTeacher]["Class"]).sort();
        populateSelect(findStudentSelect, classes, "--- Chọn một lớp học ---");
        findStudentSelect.disabled = false;
    } else {
        populateSelect(findStudentSelect, [], "--- Chọn giáo viên trước ---");
        findStudentSelect.disabled = true;
    }
});


findDatesBtn.addEventListener('click', async () => {
    // Tên biến được đổi cho rõ nghĩa hơn
    const selectedTeacher = findTeacherSelect.value;
    const selectedClass = findStudentSelect.value; // Đây là tên lớp
    const selectedCourse = findCourseSelect.value;

    if (!selectedTeacher || !selectedClass || !selectedCourse) {
        alert("Vui lòng chọn đủ thông tin Giáo viên, Lớp học và Khóa.");
        return;
    }

    // 1. Đóng card tìm kiếm và bật hiệu ứng loading
    mainContainer.classList.add('refreshing');
    
    try {
        // 2. Gửi yêu cầu tìm kiếm lên backend
        const response = await fetch('/api/find-sessions', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                teacherName: selectedTeacher,
                className: selectedClass,
                courseNumber: selectedCourse
            })
        });
        
        const result = await response.json();
        if (!response.ok) throw new Error(result.error || "Lỗi không xác định từ server.");
        
        // 3. Cập nhật giao diện với dữ liệu mới
        if (Object.keys(result).length === 0) {
            alert(`Không tìm thấy buổi học nào cho "${selectedClass}" - Khóa ${selectedCourse}.`);
        } else {
            console.log("Đã tìm thấy dữ liệu, đang cập nhật danh sách bill...");
            
            console.log("AKKK")
            console.log(result);
            const sessions = result[0];
            const NumberCourses = sessions.dates.length ;   
            
            console.log(sessions);
            const option = document.createElement('option');
            const dates = sessions.dates.map(s => formatDate(s));
            option.value = `${sessions.name}|${sessions.courseNumber}`;
            option.textContent = `${sessions.name} - Khóa ${sessions.courseNumber} (${NumberCourses} buổi)`;
            option.dataset.dates = JSON.stringify(dates);
            studentSelect.append(...[option]);    
        }
            

    } catch (error) {
        alert(`Lỗi khi tìm kiếm: ${error.message}`);
    } finally {
        // 4. Tắt hiệu ứng loading
        mainContainer.classList.remove('refreshing');
    }
});

jsonInput.addEventListener('change', (e) => {
    if (e.target.files.length > 0) {
        handleFile(e.target.files[0]);
    }
});
