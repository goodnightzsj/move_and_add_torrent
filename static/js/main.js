// 全局变量
let scannedFiles = [];
let processedFiles = [];
let matchedTorrents = [];

// 页面加载时检查配置状态
document.addEventListener("DOMContentLoaded", function () {
  loadAllConfigs();
});

// 加载所有配置
async function loadAllConfigs() {
  console.log("开始加载所有配置...");

  // 并行加载所有配置
  await Promise.all([loadGeneralConfig(), loadCategoryConfig()]);

  console.log("所有配置加载完成");
}

// 加载通用配置
async function loadGeneralConfig() {
  try {
    const response = await fetch("/api/config");
    const data = await response.json();

    if (data.status === "success" && data.config) {
      const config = data.config;

      // 填入TMDB配置
      if (config.tmdb_api_key) {
        document.getElementById("tmdbApiKey").value = config.tmdb_api_key;
        updateTMDBStatus("success", "已配置");
      }

      // 填入qBittorrent配置
      if (config.qb_host) {
        document.getElementById("qbHost").value = config.qb_host;
        document.getElementById("qbUsername").value = config.qb_username || "";
        document.getElementById("qbPassword").value = config.qb_password || "";
        updateQBStatus("success", "已配置");
      }

      // 填入路径配置
      if (config.movie_path) {
        document.getElementById("moviePath").value = config.movie_path;
      }

      if (config.exclude_dirs && config.exclude_dirs.length > 0) {
        // 将数组转换为换行分隔的字符串
        document.getElementById("excludeDirs").value =
          config.exclude_dirs.join("\n");
      }

      if (config.torrent_path) {
        document.getElementById("torrentPath").value = config.torrent_path;
      }

      console.log("通用配置已自动填入");
    }
  } catch (error) {
    console.error("加载通用配置失败:", error);
  }
}

// 更新TMDB状态
function updateTMDBStatus(status, text) {
  const statusElement = document.getElementById("tmdbStatus");
  if (statusElement) {
    statusElement.className = `status-badge status-${status} ms-2`;
    statusElement.textContent = text;
  }
}

// 更新qBittorrent状态
function updateQBStatus(status, text) {
  const statusElement = document.getElementById("qbStatus");
  if (statusElement) {
    statusElement.className = `status-badge status-${status} ms-2`;
    statusElement.textContent = text;
  }
}

// 检查配置状态
async function checkConfigStatus() {
  try {
    const response = await fetch("/api/get_config_status");
    const status = await response.json();

    // 更新TMDB状态
    if (status.tmdb_configured) {
      document.getElementById("tmdbStatus").className =
        "status-badge status-success ms-2";
      document.getElementById("tmdbStatus").textContent = "已配置";
    }

    // 更新qBittorrent状态
    if (status.qb_configured) {
      document.getElementById("qbStatus").className =
        "status-badge status-success ms-2";
      document.getElementById("qbStatus").textContent = "已配置";
    }

    // 显示已处理文件数量
    if (status.processed_files_count > 0) {
      showMessage(
        "processResults",
        `系统已加载 ${status.processed_files_count} 个已处理文件的记录`,
        "info"
      );
    }

    console.log("配置状态:", status);
  } catch (error) {
    console.error("获取配置状态失败:", error);
  }
}

// 工具函数
function showLoading(elementId) {
  document.getElementById(elementId).style.display = "block";
}

function hideLoading(elementId) {
  document.getElementById(elementId).style.display = "none";
}

function showMessage(containerId, message, type = "info") {
  const container = document.getElementById(containerId);
  const alertClass =
    type === "error"
      ? "alert-danger"
      : type === "success"
      ? "alert-success"
      : type === "warning"
      ? "alert-warning"
      : "alert-info";

  container.innerHTML = `
        <div class="alert ${alertClass} alert-dismissible fade show" role="alert">
            ${message}
            <button type="button" class="btn-close" data-bs-dismiss="alert"></button>
        </div>
    `;
}

function formatFileSize(bytes) {
  if (bytes === 0) return "0 Bytes";
  const k = 1024;
  const sizes = ["Bytes", "KB", "MB", "GB", "TB"];
  const i = Math.floor(Math.log(bytes) / Math.log(k));
  return parseFloat((bytes / Math.pow(k, i)).toFixed(2)) + " " + sizes[i];
}

// 配置TMDB API
async function configTMDB() {
  const apiKey = document.getElementById("tmdbApiKey").value.trim();

  if (!apiKey) {
    showMessage("tmdbStatus", "请输入TMDB API密钥", "error");
    return;
  }

  try {
    const response = await fetch("/api/config_tmdb", {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify({
        tmdb_api_key: apiKey,
      }),
    });

    const result = await response.json();

    if (response.ok) {
      document.getElementById("tmdbStatus").className =
        "status-badge status-success ms-2";
      document.getElementById("tmdbStatus").textContent = "已配置";
      showMessage("tmdbStatus", result.message, "success");
    } else {
      document.getElementById("tmdbStatus").className =
        "status-badge status-error ms-2";
      document.getElementById("tmdbStatus").textContent = "配置失败";
      showMessage("tmdbStatus", result.message, "error");
    }
  } catch (error) {
    console.error("配置TMDB失败:", error);
    showMessage("tmdbStatus", "配置失败: " + error.message, "error");
  }
}

// 配置qBittorrent
async function configQB() {
  const host = document.getElementById("qbHost").value.trim();
  const username = document.getElementById("qbUsername").value.trim();
  const password = document.getElementById("qbPassword").value.trim();

  if (!host || !username || !password) {
    showMessage("qbStatus", "请填写完整的qBittorrent配置信息", "error");
    return;
  }

  try {
    const response = await fetch("/api/config_qb", {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify({
        qb_host: host,
        qb_username: username,
        qb_password: password,
      }),
    });

    const result = await response.json();

    if (response.ok) {
      document.getElementById("qbStatus").className =
        "status-badge status-success ms-2";
      document.getElementById("qbStatus").textContent = "已配置";
      showMessage("qbStatus", result.message, "success");
    } else {
      document.getElementById("qbStatus").className =
        "status-badge status-error ms-2";
      document.getElementById("qbStatus").textContent = "配置失败";
      showMessage("qbStatus", result.message, "error");
    }
  } catch (error) {
    console.error("配置qBittorrent失败:", error);
    showMessage("qbStatus", "配置失败: " + error.message, "error");
  }
}

// 加载分类配置
async function loadCategoryConfig() {
  try {
    updateCategoryStatus("pending", "加载中...");

    const response = await fetch("/api/category-config");
    const data = await response.json();

    if (data.status === "success" && data.config_text) {
      document.getElementById("categoryConfig").value = data.config_text;
      updateCategoryStatus("success", "已加载");
      console.log("分类配置已自动加载");
    } else {
      updateCategoryStatus("error", "加载失败");
      console.error("分类配置加载失败:", data);
    }
  } catch (error) {
    console.error("加载分类配置失败:", error);
    updateCategoryStatus("error", "加载失败");
  }
}

// 保存分类配置
async function configCategory() {
  const configText = document.getElementById("categoryConfig").value;

  if (!configText.trim()) {
    alert("请输入分类配置");
    return;
  }

  updateCategoryStatus("pending", "保存中...");

  try {
    const response = await fetch("/api/category-config", {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify({
        config_text: configText,
      }),
    });

    const data = await response.json();

    if (data.status === "success") {
      updateCategoryStatus("success", "保存成功");
      alert("分类配置保存成功！");
    } else {
      updateCategoryStatus("error", "保存失败");
      alert("保存失败：" + data.message);
    }
  } catch (error) {
    console.error("保存分类配置失败:", error);
    updateCategoryStatus("error", "保存失败");
    alert("保存失败：网络错误");
  }
}

// 更新分类配置状态
function updateCategoryStatus(status, text) {
  const statusElement = document.getElementById("categoryStatus");
  statusElement.className = `status-badge status-${status} ms-2`;
  statusElement.textContent = text;
}

// 保存路径配置
async function savePathConfig(moviePath, excludeDirs, torrentPath) {
  try {
    const configData = {};

    if (moviePath !== null) {
      configData.movie_path = moviePath;
    }

    if (excludeDirs !== null) {
      configData.exclude_dirs = excludeDirs;
    }

    if (torrentPath !== null) {
      configData.torrent_path = torrentPath;
    }

    // 只有当有配置需要保存时才发送请求
    if (Object.keys(configData).length > 0) {
      const response = await fetch("/api/config", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify(configData),
      });

      const result = await response.json();
      if (result.status === "success") {
        console.log("路径配置已保存");
      } else {
        console.error("保存路径配置失败:", result.message);
      }
    }
  } catch (error) {
    console.error("保存路径配置失败:", error);
  }
}

// 扫描影视文件
async function scanMovies() {
  const path = document.getElementById("moviePath").value.trim();
  const excludeDirs = document.getElementById("excludeDirs").value.trim();

  if (!path) {
    showMessage("scanResults", "请输入影视文件路径", "error");
    return;
  }

  // 支持逗号分隔和换行分隔
  const excludeList = excludeDirs
    ? excludeDirs
        .split(/[,\n]/)
        .map((s) => s.trim())
        .filter((s) => s.length > 0)
    : [];

  // 保存路径配置
  await savePathConfig(path, excludeList, null);

  showLoading("scanLoading");

  try {
    const response = await fetch("/api/scan", {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify({
        path: path,
        exclude_dirs: excludeList,
      }),
    });

    const result = await response.json();
    hideLoading("scanLoading");

    if (response.ok) {
      scannedFiles = result.files;
      window.scannedDirectories = result.directories; // 保存扫描到的目录
      displayScanResults(result);
      document.getElementById("processBtn").disabled = false;
    } else {
      showMessage("scanResults", result.error, "error");
    }
  } catch (error) {
    hideLoading("scanLoading");
    console.error("扫描文件失败:", error);
    showMessage("scanResults", "扫描失败: " + error.message, "error");
  }
}

// 显示扫描结果
function displayScanResults(result) {
  const container = document.getElementById("scanResults");

  console.log("显示扫描结果:", result);

  let html = `
        <div class="alert alert-success">
            <h6><i class="bi bi-check-circle"></i> 扫描完成</h6>
            <p>找到 ${result.total_files} 个文件，${result.total_dirs} 个目录</p>
        </div>
        <div class="file-list">
    `;

  // 检查数据是否存在
  if (!result.directories || !result.files) {
    html += `
      <div class="alert alert-warning">
        <p>数据结构异常：directories=${!!result.directories}, files=${!!result.files}</p>
      </div>
    `;
  } else {
    console.log("目录数量:", result.directories.length);
    console.log("文件数量:", result.files.length);

    // 显示目录（文件夹）
    if (result.directories && result.directories.length > 0) {
      result.directories.forEach((dir, index) => {
        console.log(`目录${index}:`, dir);
        html += `
                <div class="file-item">
                    <div>
                        <i class="bi bi-folder-fill text-warning"></i>
                        <strong>${dir.name || "未知目录"}</strong>
                        <small class="text-muted">(文件夹)</small>
                    </div>
                    <span class="badge bg-warning">目录</span>
                </div>
            `;
      });
    }

    // 显示视频文件
    const videoExtensions = [
      ".mp4",
      ".mkv",
      ".avi",
      ".mov",
      ".wmv",
      ".flv",
      ".webm",
      ".m4v",
      ".ts",
      ".m2ts",
      ".mts",
      ".vob",
      ".mpg",
      ".mpeg",
      ".3gp",
      ".f4v",
    ];

    if (result.files && result.files.length > 0) {
      const videoFiles = result.files.filter((file) =>
        videoExtensions.includes(file.extension.toLowerCase())
      );

      console.log("视频文件数量:", videoFiles.length);

      videoFiles.forEach((file, index) => {
        console.log(`视频文件${index}:`, file);
        html += `
                <div class="file-item">
                    <div>
                        <i class="bi bi-film"></i>
                        <strong>${file.name || "未知文件"}</strong>
                        <small class="text-muted">(${formatFileSize(
                          file.size || 0
                        )})</small>
                    </div>
                    <span class="badge bg-primary">${
                      file.extension || "unknown"
                    }</span>
                </div>
            `;
      });

      // 如果没有视频文件，显示所有文件
      if (videoFiles.length === 0) {
        html += `
          <div class="alert alert-info">
            <p>没有找到视频文件，显示所有文件：</p>
          </div>
        `;
        result.files.forEach((file, index) => {
          console.log(`所有文件${index}:`, file);
          html += `
                  <div class="file-item">
                      <div>
                          <i class="bi bi-file-earmark"></i>
                          <strong>${file.name || "未知文件"}</strong>
                          <small class="text-muted">(${formatFileSize(
                            file.size || 0
                          )})</small>
                      </div>
                      <span class="badge bg-secondary">${
                        file.extension || "unknown"
                      }</span>
                  </div>
              `;
        });
      }
    }
  }

  html += "</div>";
  container.innerHTML = html;

  console.log("HTML已设置到容器");
}

// 处理文件分类
async function processFiles() {
  if (
    scannedFiles.length === 0 &&
    (!window.scannedDirectories || window.scannedDirectories.length === 0)
  ) {
    showMessage("processResults", "请先扫描文件", "error");
    return;
  }

  const basePath = document.getElementById("moviePath").value.trim();

  // 准备要处理的项目（文件夹和视频文件）
  let itemsToProcess = [];

  // 添加文件夹
  if (window.scannedDirectories) {
    itemsToProcess = itemsToProcess.concat(window.scannedDirectories);
  }

  // 添加视频文件
  const videoExtensions = [
    ".mp4",
    ".mkv",
    ".avi",
    ".mov",
    ".wmv",
    ".flv",
    ".webm",
    ".m4v",
    ".ts",
    ".m2ts",
    ".mts",
    ".vob",
    ".mpg",
    ".mpeg",
    ".3gp",
    ".f4v",
  ];
  const videoFiles = scannedFiles.filter((file) =>
    videoExtensions.includes(file.extension.toLowerCase())
  );

  itemsToProcess = itemsToProcess.concat(videoFiles);

  showLoading("processLoading");

  try {
    const response = await fetch("/api/process", {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify({
        base_path: basePath,
        files: itemsToProcess,
      }),
    });

    const result = await response.json();
    hideLoading("processLoading");

    if (response.ok) {
      processedFiles = result.results;
      displayProcessResults(result.results);
    } else {
      showMessage("processResults", result.error, "error");
    }
  } catch (error) {
    hideLoading("processLoading");
    console.error("处理文件失败:", error);
    showMessage("processResults", "处理失败: " + error.message, "error");
  }
}

// 显示处理结果
function displayProcessResults(results) {
  const container = document.getElementById("processResults");

  const successCount = results.filter((r) => r.status === "success").length;
  const errorCount = results.filter((r) => r.status === "error").length;

  let html = `
        <div class="alert alert-info">
            <h6><i class="bi bi-info-circle"></i> 处理完成</h6>
            <p>成功处理 ${successCount} 个文件，失败 ${errorCount} 个文件</p>
        </div>
    `;

  results.forEach((result) => {
    const itemClass = result.status === "success" ? "success" : "error";
    const icon =
      result.status === "success" ? "bi-check-circle" : "bi-x-circle";

    html += `
            <div class="result-item ${itemClass}">
                <div class="d-flex justify-content-between align-items-center">
                    <div>
                        <i class="bi ${icon}"></i>
                        <strong>${result.filename}</strong>
                        ${
                          result.category
                            ? `<span class="badge bg-primary ms-2">${result.category}</span>`
                            : ""
                        }
                    </div>
                    <small class="text-muted">${
                      result.status === "success" ? "已分类" : result.message
                    }</small>
                </div>
                ${
                  result.new_path
                    ? `<small class="text-muted d-block mt-1">新路径: ${result.new_path}</small>`
                    : ""
                }
            </div>
        `;
  });

  container.innerHTML = html;
}

// 匹配种子文件
async function matchTorrents() {
  const torrentPath = document.getElementById("torrentPath").value.trim();

  if (!torrentPath) {
    showMessage("matchResults", "请输入种子文件夹路径", "error");
    return;
  }

  // 保存种子路径配置
  await savePathConfig(null, null, torrentPath);

  showLoading("matchLoading");

  try {
    const response = await fetch("/api/match_torrents", {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify({
        torrent_path: torrentPath,
      }),
    });

    const result = await response.json();
    hideLoading("matchLoading");

    if (response.ok) {
      // 为每个匹配的种子添加选择状态，保持后端设置的状态或默认为选中
      matchedTorrents = result.matched.map(item => ({
        ...item,
        selected: item.selected !== undefined ? item.selected : true
      }));
      displayMatchResults(result);
      updateAddButton();
    } else {
      showMessage("matchResults", result.error, "error");
    }
  } catch (error) {
    hideLoading("matchLoading");
    console.error("匹配种子失败:", error);
    showMessage("matchResults", "匹配失败: " + error.message, "error");
  }
}

// 显示匹配结果
function displayMatchResults(result) {
  // 使用新的显示逻辑
  updateMatchDisplay();

  // 显示未匹配的种子
  if (result.unmatched.length > 0) {
    const container = document.getElementById("matchResults");
    let currentHtml = container.innerHTML;

    currentHtml += '<h6 class="mt-3"><i class="bi bi-x-circle text-warning"></i> 未匹配的种子</h6>';
    result.unmatched.forEach((torrent) => {
      currentHtml += `
                <div class="result-item">
                    <div class="d-flex justify-content-between align-items-center">
                        <div>
                            <i class="bi bi-file-earmark"></i>
                            <strong>${torrent.name}</strong>
                        </div>
                        <span class="badge bg-warning">未匹配</span>
                    </div>
                    <small class="text-muted">提取标题: ${torrent.title}</small>
                </div>
            `;
    });

    container.innerHTML = currentHtml;
  }
}

// 更新添加按钮状态
function updateAddButton() {
  const selectedCount = matchedTorrents.filter(item => item.selected).length;
  const addBtn = document.getElementById("addTorrentsBtn");

  addBtn.disabled = selectedCount === 0;
  addBtn.innerHTML = `<i class="bi bi-plus-circle"></i> 批量添加种子 (${selectedCount})`;
}

// 移除种子
async function removeTorrent(index) {
  if (index >= 0 && index < matchedTorrents.length) {
    const match = matchedTorrents[index];

    // 标记为未选择
    matchedTorrents[index].selected = false;

    // 记录移除的种子信息
    try {
      const response = await fetch("/api/remove_torrent", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify({
          torrent_info: match.torrent,
          matched_info: {
            name: match.matched_filename,
            similarity: match.similarity,
            match_type: match.matched_file.match_type,
            download_path: match.matched_file.download_path
          }
        }),
      });

      if (response.ok) {
        console.log("种子移除记录成功");
      } else {
        console.warn("种子移除记录失败");
      }
    } catch (error) {
      console.error("记录移除种子失败:", error);
    }

    updateMatchDisplay();
    updateAddButton();
  }
}

// 恢复种子
function restoreTorrent(index) {
  if (index >= 0 && index < matchedTorrents.length) {
    matchedTorrents[index].selected = true;
    updateMatchDisplay();
    updateAddButton();
  }
}

// 更新匹配结果显示
function updateMatchDisplay() {
  const container = document.getElementById("matchResults");
  const selectedTorrents = matchedTorrents.filter(item => item.selected);
  const removedTorrents = matchedTorrents.filter(item => !item.selected);

  // 过滤出需要显示的种子（排除100%匹配的种子）
  const displayTorrents = selectedTorrents.filter(match => {
    const similarity = Math.round(match.similarity * 100);
    return similarity < 100;
  });

  // 统计100%匹配的种子数量
  const perfectMatchCount = selectedTorrents.length - displayTorrents.length;

  let html = `
        <div class="alert alert-info">
            <h6><i class="bi bi-info-circle"></i> 匹配完成</h6>
            <p>总计选择 ${selectedTorrents.length} 个种子（其中 ${perfectMatchCount} 个完美匹配，${displayTorrents.length} 个需要确认），已移除 ${removedTorrents.length} 个种子</p>
        </div>
    `;

  // 显示已选择的种子（排除100%匹配）
  if (displayTorrents.length > 0) {
    html += '<h6><i class="bi bi-check-circle text-success"></i> 已选择的种子（需要确认）</h6>';
    displayTorrents.forEach((match) => {
      const originalIndex = matchedTorrents.findIndex(item => item === match);
      const similarity = Math.round(match.similarity * 100);
      html += `
                <div class="match-item">
                    <div class="d-flex justify-content-between align-items-center mb-2">
                        <strong>${match.torrent.name}</strong>
                        <div>
                            <span class="badge bg-success me-2">${similarity}% 匹配</span>
                            <button class="btn btn-sm btn-outline-danger" onclick="removeTorrent(${originalIndex})" title="移除此种子">
                                <i class="bi bi-x"></i>
                            </button>
                        </div>
                    </div>
                    <div class="similarity-bar mb-2">
                        <div class="similarity-fill" style="width: ${similarity}%"></div>
                    </div>
                    <small class="text-muted">
                        匹配文件夹: <strong>${match.matched_filename || '未知文件夹'}</strong><br>
                        匹配策略: ${match.matched_file.match_type === 'folder_similar' ? '文件与文件夹相似' : '文件与文件夹不同'}<br>
                        示例文件: ${match.matched_file.sample_file || '无'} (共${match.matched_file.file_count || 0}个文件)<br>
                        下载路径: ${match.matched_file.download_path || '未知路径'}
                    </small>
                </div>
            `;
    });
  }

  // 显示100%匹配的种子提示
  if (perfectMatchCount > 0) {
    html += `
      <div class="alert alert-success mt-3">
        <i class="bi bi-check-circle-fill"></i>
        <strong>${perfectMatchCount} 个种子完美匹配（100%）</strong>，已自动选择，无需手动确认
      </div>
    `;
  }

  // 显示已移除的种子
  if (removedTorrents.length > 0) {
    html += '<h6 class="mt-3"><i class="bi bi-x-circle text-muted"></i> 已移除的种子</h6>';
    removedTorrents.forEach((match) => {
      const originalIndex = matchedTorrents.findIndex(item => item === match);
      const similarity = Math.round(match.similarity * 100);
      html += `
                <div class="match-item" style="opacity: 0.6;">
                    <div class="d-flex justify-content-between align-items-center mb-2">
                        <strong>${match.torrent.name}</strong>
                        <div>
                            <span class="badge bg-secondary me-2">${similarity}% 匹配</span>
                            <button class="btn btn-sm btn-outline-success" onclick="restoreTorrent(${originalIndex})" title="恢复此种子">
                                <i class="bi bi-arrow-counterclockwise"></i>
                            </button>
                        </div>
                    </div>
                    <small class="text-muted">
                        匹配文件夹: <strong>${match.matched_filename || '未知文件夹'}</strong><br>
                        匹配策略: ${match.matched_file.match_type === 'folder_similar' ? '文件与文件夹相似' : '文件与文件夹不同'}
                    </small>
                </div>
            `;
    });
  }

  container.innerHTML = html;
}

// 添加种子到qBittorrent
async function addTorrents() {
  const selectedTorrents = matchedTorrents.filter(item => item.selected);

  if (selectedTorrents.length === 0) {
    showMessage("addResults", "没有选择的种子可以添加", "error");
    return;
  }

  showLoading("addLoading");

  try {
    const response = await fetch("/api/add_torrents", {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify({
        matched_torrents: selectedTorrents,
      }),
    });

    const result = await response.json();
    hideLoading("addLoading");

    if (response.ok) {
      displayAddResults(result.results);
    } else {
      showMessage("addResults", result.error, "error");
    }
  } catch (error) {
    hideLoading("addLoading");
    console.error("添加种子失败:", error);
    showMessage("addResults", "添加失败: " + error.message, "error");
  }
}

// 显示添加结果
function displayAddResults(results) {
  const container = document.getElementById("addResults");

  const successCount = results.filter((r) => r.status === "success").length;
  const errorCount = results.filter((r) => r.status === "error").length;

  let html = `
        <div class="alert alert-info">
            <h6><i class="bi bi-info-circle"></i> 添加完成</h6>
            <p>成功添加 ${successCount} 个种子，失败 ${errorCount} 个种子</p>
        </div>
    `;

  results.forEach((result) => {
    const itemClass = result.status === "success" ? "success" : "error";
    const icon =
      result.status === "success" ? "bi-check-circle" : "bi-x-circle";

    html += `
            <div class="result-item ${itemClass}">
                <div class="d-flex justify-content-between align-items-center">
                    <div>
                        <i class="bi ${icon}"></i>
                        <strong>${result.torrent_name}</strong>
                    </div>
                    <small class="text-muted">${
                      result.status === "success" ? "已添加" : result.message
                    }</small>
                </div>
                ${
                  result.download_path
                    ? `<small class="text-muted d-block mt-1">下载路径: ${result.download_path}</small>`
                    : ""
                }
            </div>
        `;
  });

  container.innerHTML = html;
}

// 重置数据
async function resetData() {
  if (
    !confirm("确定要重置所有数据吗？这将清空已处理文件的记录，此操作不可撤销！")
  ) {
    return;
  }

  try {
    const response = await fetch("/api/reset_data", {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
    });

    const result = await response.json();

    if (response.ok) {
      showMessage("systemResults", result.message, "success");
      // 清空前端数据
      scannedFiles = [];
      processedFiles = [];
      matchedTorrents = [];
      // 清空显示区域
      document.getElementById("scanResults").innerHTML = "";
      document.getElementById("processResults").innerHTML = "";
      document.getElementById("matchResults").innerHTML = "";
      document.getElementById("addResults").innerHTML = "";
      // 禁用按钮
      document.getElementById("processBtn").disabled = true;
      const addBtn = document.getElementById("addTorrentsBtn");
      addBtn.disabled = true;
      addBtn.innerHTML = '<i class="bi bi-plus-circle"></i> 批量添加种子';
    } else {
      showMessage("systemResults", result.message, "error");
    }
  } catch (error) {
    console.error("重置数据失败:", error);
    showMessage("systemResults", "重置数据失败: " + error.message, "error");
  }
}
