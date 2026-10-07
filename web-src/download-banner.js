// chat.leoh.top 顶部的“下载 App”提示条：手机浏览器才显示，可关闭（记住 30 天）
(function () {
  var KEY = 'leoh-download-banner-dismissed';
  var ua = navigator.userAgent || '';
  if (!/Android|iPhone|iPad|iPod/i.test(ua)) return;
  try {
    var t = Number(localStorage.getItem(KEY) || 0);
    if (Date.now() - t < 30 * 86400e3) return;
  } catch (e) { /* 隐私模式没有 localStorage，照常显示 */ }

  var bar = document.createElement('div');
  bar.setAttribute('role', 'region');
  bar.setAttribute('aria-label', '下载 leoh-chat App');
  bar.style.cssText = 'position:fixed;left:0;right:0;bottom:0;z-index:2147483647;display:flex;align-items:center;' +
    'gap:10px;padding:10px 12px;background:#0E9F8A;color:#fff;font:15px/1.4 -apple-system,"PingFang SC",sans-serif;' +
    'box-shadow:0 -2px 8px rgba(0,0,0,.2)';

  var icon = document.createElement('img');
  icon.src = '/icon.png'; icon.alt = ''; icon.width = 32; icon.height = 32;
  icon.style.borderRadius = '8px';

  var text = document.createElement('span');
  text.textContent = /Android/i.test(ua) ? '用 leoh-chat App 收消息更及时' : 'iPhone 可在 App Store 安装客户端';
  text.style.flex = '1';

  var go = document.createElement('a');
  go.href = '/download'; go.textContent = '下载';
  go.style.cssText = 'color:#0E9F8A;background:#fff;border-radius:16px;padding:6px 14px;text-decoration:none;font-weight:600';

  var close = document.createElement('button');
  close.type = 'button'; close.textContent = '×';
  close.setAttribute('aria-label', '关闭提示');
  close.style.cssText = 'background:none;border:0;color:#fff;font-size:22px;line-height:1;padding:4px 6px;cursor:pointer';
  close.onclick = function () {
    try { localStorage.setItem(KEY, String(Date.now())); } catch (e) {}
    bar.remove();
  };

  bar.append(icon, text, go, close);
  document.body.appendChild(bar);
})();
