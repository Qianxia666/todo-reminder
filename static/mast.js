/* 页眉日期：按北京时间写日期，避免与服务端时区不一致 */
(function () {
    var el = document.getElementById('mast-date');
    if (!el) return;
    var now = new Date();
    var d = new Intl.DateTimeFormat('zh-CN', {
        timeZone: 'Asia/Shanghai', year: 'numeric', month: 'numeric', day: 'numeric'
    }).format(now);
    var w = new Intl.DateTimeFormat('zh-CN', {
        timeZone: 'Asia/Shanghai', weekday: 'long'
    }).format(now);
    el.textContent = d.replace(/\//g, '-') + ' · ' + w;
})();
