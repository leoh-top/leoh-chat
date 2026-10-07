// chat.leoh.top 以前是 Cinny 网页版，它注册过 /sw.js。换成 leoh-chat 网页版后，用这个空的 Service Worker
// 顶替并注销自己，让老浏览器不再被旧缓存卡住。
self.addEventListener('install', () => self.skipWaiting());
self.addEventListener('activate', (event) => {
  event.waitUntil((async () => {
    await self.registration.unregister();
    const clients = await self.clients.matchAll({ type: 'window' });
    for (const c of clients) c.navigate(c.url);
  })());
});
