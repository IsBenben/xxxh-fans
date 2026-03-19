// 请将 UID 替换为你的 B站 UID
const API_URL = `https://api.codetabs.com/v1/proxy/?quest=https://api.bilibili.com/x/relation/stat?vmid=${BILIBILI_UID}`;

const fansDisplay = document.getElementById('fansDisplay');
const progressFill = document.getElementById('progressFill');
const changeToast = document.getElementById('changeToast');

let currentFans = parseInt(fansDisplay.innerText, 10);

function updateProgress(fans) {
    const percent = (fans / TOTAL_GOAL) * 100;
    progressFill.style.width = `${percent.toFixed(2)}%`;
}

function showChange(change) {
    if (change === 0) return;
    const sign = change > 0 ? '+' : '';
    changeToast.textContent = `${sign}${change}`;
    changeToast.classList.add('show');
    setTimeout(() => {
        changeToast.classList.remove('show');
    }, 500);
}

async function fetchFans() {
    try {
        // 添加一个包含常见浏览器请求头的对象
        const response = await fetch(API_URL + '&time=' + Date.now());
        const data = await response.json();
        if (data.code === 0) {
            const newFans = data.data.follower;
            if (newFans !== currentFans) {
                const change = newFans - currentFans;
                currentFans = newFans;
                fansDisplay.innerText = newFans;
                updateProgress(newFans);
                showChange(change);
            }
        } else {
            console.error('API error:', data);
        }
    } catch (error) {
        console.error('Fetch failed:', error);
    }
    setTimeout(() => {
        fetchFans();
    }, 5000);
}

// 初始化进度条
updateProgress(currentFans);

// 立即获取一次最新数据（可选，保证打开页面时与真实值同步）
fetchFans();
