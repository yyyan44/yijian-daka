/* 手机版界面逻辑 v1.1
 * 这一版修掉的问题：
 *   #1 选好的图存进 IndexedDB —— 切出去/被杀掉，回来还在
 *   #2 同名覆盖（Java 端删旧文件）
 *   #3 「打开」按钮（用手机上的办公软件打开刚生成的文档）
 *   #4 进度条
 *   #5 生成前检查班级/姓名
 *   #6 设置边输边存
 *   #7 缩略图带 × 按钮
 *   #8 长按日期卡片 = 清空该天（可重新选）
 *   #11 未归位卡片标注属于第几周
 *   #12 措辞统一成「周日/周一…」
 *   #13 第 1 周周一改成日期选择器
 *   #14 文件名带「通知/转发」的自动进备用格
 *   #18 返回键先关大图预览
 */
(function () {
  'use strict';

  var C = window.DakaCore, D = window.DakaDocx;
  var DAYS = C.DAYS;
  var CFG_KEY = 'daka.cfg.v2';
  var WEEK_KEY = 'daka.week.v2';

  var state = {
    cfg: loadCfg(),
    week: loadWeek(),   // 周次完全由你定（默认本周），不从截图日期推
    chat: {},           // 星期 → [shot]
    dates: [],          // 备用格
    pickTarget: null,
    last: null,
    busy: false
  };
  DAYS.forEach(function (wd) { state.chat[wd] = []; });

  function loadWeek() {
    try {
      var w = parseInt(localStorage.getItem(WEEK_KEY), 10);
      return w > 0 ? w : null;
    } catch (e) { return null; }
  }

  // ───────── 配置 ─────────
  function loadCfg() {
    var base = Object.assign({}, C.DEFAULT_CFG);
    try {
      var s = JSON.parse(localStorage.getItem(CFG_KEY) || '{}');
      Object.keys(base).forEach(function (k) { if (s[k] !== undefined && s[k] !== '') base[k] = s[k]; });
    } catch (e) { /* 忽略 */ }
    return base;
  }
  function saveCfg() {
    try { localStorage.setItem(CFG_KEY, JSON.stringify(state.cfg)); } catch (e) { /* 忽略 */ }
  }

  // ───────── 选中的图持久化（IndexedDB）─────────
  var IDB = (function () {
    var dbp = null;
    function open() {
      if (dbp) return dbp;
      dbp = new Promise(function (resolve, reject) {
        if (!window.indexedDB) { reject(new Error('这台设备的 WebView 不支持 IndexedDB')); return; }
        var r = indexedDB.open('daka-picks', 1);
        r.onupgradeneeded = function () {
          var db = r.result;
          if (!db.objectStoreNames.contains('picks')) db.createObjectStore('picks', { keyPath: 'uid' });
        };
        r.onsuccess = function () { resolve(r.result); };
        r.onerror = function () { reject(r.error); };
      });
      return dbp;
    }
    function tx(mode, fn) {
      return open().then(function (db) {
        return new Promise(function (resolve, reject) {
          var t = db.transaction('picks', mode);
          var st = t.objectStore('picks');
          var out = fn(st);
          t.oncomplete = function () { resolve(out && out.result !== undefined ? out.result : undefined); };
          t.onerror = function () { reject(t.error); };
        });
      });
    }
    return {
      all: function () {
        return tx('readonly', function (st) { return st.getAll(); }).then(function (v) { return v || []; });
      },
      put: function (rec) { return tx('readwrite', function (st) { st.put(rec); }); },
      del: function (uid) { return tx('readwrite', function (st) { st.delete(uid); }); },
      clear: function () { return tx('readwrite', function (st) { st.clear(); }); }
    };
  })();

  var uidSeq = 1;
  function persistAll() {
    var recs = [];
    function add(area, wd, list) {
      list.forEach(function (s) {
        if (!s.uid) s.uid = 'u' + (Date.now()) + '-' + (uidSeq++);
        recs.push({ uid: s.uid, area: area, wd: wd || '', name: s.name, lastModified: s.file.lastModified || 0, blob: s.file });
      });
    }
    DAYS.forEach(function (wd) { add('chat', wd, state.chat[wd]); });
    add('dates', '', state.dates);
    try { localStorage.setItem(WEEK_KEY, String(state.week == null ? '' : state.week)); } catch (e) { /* 忽略 */ }
    return IDB.clear().then(function () {
      return recs.reduce(function (p, r) { return p.then(function () { return IDB.put(r); }); }, Promise.resolve());
    }).catch(function (e) {
      log('（提示：本地保存失败，' + (e && e.message ? e.message : e) + '）');
    });
  }

  function restore() {
    return IDB.all().then(function (recs) {
      if (!recs.length) return false;
      recs.forEach(function (r) {
        var file = new File([r.blob], r.name, { lastModified: r.lastModified, type: r.blob.type || 'image/*' });
        var shot = C.makeShot(file, state.cfg);
        shot.uid = r.uid;
        if (r.area === 'dates') state.dates.push(shot);
        else if (r.area === 'leftover') state.chat[shot.weekday].push(shot);  // 老数据：以前放"未归位"的，现在按周几收回去
        else if (state.chat[r.wd]) state.chat[r.wd].push(shot);
      });
      return true;
    }).catch(function () { return false; });
  }

  // ───────── 小工具 ─────────
  var $ = function (id) { return document.getElementById(id); };
  function el(tag, cls, text) {
    var e = document.createElement(tag);
    if (cls) e.className = cls;
    if (text != null) e.textContent = text;
    return e;
  }
  var logBuf = [];
  function log(msg) {
    if (!msg) logBuf = [];
    else {
      logBuf.push(msg);
      if (logBuf.length > 5) logBuf.shift();
    }
    var box = $('log');
    box.textContent = logBuf.join('\n');
    box.style.display = logBuf.length ? 'block' : 'none';
  }
  function allShots() {
    var a = [];
    DAYS.forEach(function (wd) { a = a.concat(state.chat[wd]); });
    return a.concat(state.dates);
  }
  // ───────── 选图 ─────────
  function openPicker(target) {
    state.pickTarget = target;
    var input = $('fileInput');
    input.value = '';
    input.click();
  }

  function onFilesPicked(files) {
    if (!files || !files.length) { log('没选到图。'); return; }
    var target = state.pickTarget || 'auto';
    var shots = Array.prototype.map.call(files, function (f) { return C.makeShot(f, state.cfg); });

    if (target === 'dates') {
      state.dates = state.dates.concat(shots);
      log('已加入备用格 ' + shots.length + ' 张。');
    } else if (target !== 'auto') {
      state.chat[target] = state.chat[target].concat(shots);
      log('已加入周' + target + ' ' + shots.length + ' 张。');
    } else {
      // 文件名带「通知/转发」的当日期截图，直接进备用格
      var notice = shots.filter(function (s) { return /通知|转发/.test(s.name); });
      var rest = shots.filter(function (s) { return notice.indexOf(s) < 0; });
      if (notice.length) state.dates = state.dates.concat(notice);

      // 只按「星期几」归位，不看这张图属于哪一周
      var r = C.classify(rest);
      DAYS.forEach(function (wd) { state.chat[wd] = state.chat[wd].concat(r.chat[wd]); });

      var detail = DAYS.filter(function (wd) { return r.chat[wd].length; })
        .map(function (wd) { return '周' + wd + ' ' + r.chat[wd].length + ' 张'; }).join('、');
      var msg = '收到 ' + shots.length + ' 张：' + (detail || '0 张');
      if (notice.length) msg += '，另有 ' + notice.length + ' 张按「通知/转发」进了备用格';
      log(msg + '。');
    }
    persistAll().then(render);
  }

  function removeShot(shot) {
    DAYS.forEach(function (wd) {
      state.chat[wd] = state.chat[wd].filter(function (x) { return x !== shot; });
    });
    state.dates = state.dates.filter(function (x) { return x !== shot; });
    if (shot.__url) URL.revokeObjectURL(shot.__url);
    if (shot.uid) IDB.del(shot.uid);
    persistAll().then(render);
  }

  function clearDay(wd) {
    var n = state.chat[wd].length;
    if (!n) return;
    if (!confirm('清空周' + wd + ' 的 ' + n + ' 张图？（可以重新选）')) return;
    state.chat[wd].slice().forEach(function (s) { removeShot(s); });
  }

  function preview(shot) {
    if (!shot.__url) shot.__url = URL.createObjectURL(shot.file);
    $('bigImg').src = shot.__url;
    $('preview').style.display = 'flex';
    history.pushState({ dakaPreview: 1 }, '');      // #18 让返回键先关预览
  }
  function closePreview() {
    $('preview').style.display = 'none';
  }

  // ───────── 渲染 ─────────
  function thumb(shot) {
    var d = el('div', 'thumb');
    var img = el('img');
    if (!shot.__url) shot.__url = URL.createObjectURL(shot.file);
    img.src = shot.__url;
    img.alt = shot.name;
    d.appendChild(img);
    var x = el('span', 'x', '×');
    x.addEventListener('click', function (e) { e.stopPropagation(); removeShot(shot); });
    d.appendChild(x);
    d.addEventListener('click', function (e) { e.stopPropagation(); preview(shot); });
    return d;
  }

  function dayCard(wd) {
    var list = state.chat[wd];
    var card = el('div', 'card day' + (list.length ? ' filled' : ' empty'));
    var head = el('div', 'row');
    var title = el('div', 'title', '周' + wd);
    var d = state.week ? C.addDays(C.cycleStart(state.week, state.cfg), DAYS.indexOf(wd)) : null;
    if (d) title.appendChild(el('span', 'date', (d.getMonth() + 1) + '/' + d.getDate()));
    head.appendChild(title);
    head.appendChild(el('span', 'chip ' + (list.length ? 'ok' : 'warn'),
      list.length ? list.length + ' 张' : '缺'));
    card.appendChild(head);

    var box = el('div', 'thumbs');
    list.forEach(function (s) { box.appendChild(thumb(s)); });
    if (!list.length) box.appendChild(el('div', 'hint', '点这张卡片补图'));
    card.appendChild(box);

    card.addEventListener('click', function () { openPicker(wd); });
    var timer = null;
    card.addEventListener('touchstart', function () {
      timer = setTimeout(function () { timer = null; clearDay(wd); }, 800);
    }, { passive: true });
    card.addEventListener('touchend', function () { if (timer) { clearTimeout(timer); timer = null; } });
    card.addEventListener('touchmove', function () { if (timer) { clearTimeout(timer); timer = null; } });
    return card;
  }

  function trayCard(kind, titleText, hintText, list, onPick) {
    var card = el('div', 'card tray' + (list.length ? ' filled' : ''));
    var head = el('div', 'row');
    head.appendChild(el('div', 'title', titleText));
    head.appendChild(el('span', 'chip ' + (list.length ? 'ok' : 'idle'), list.length + ' 张'));
    card.appendChild(head);
    var box = el('div', 'thumbs');
    list.forEach(function (s) { box.appendChild(thumb(s)); });
    if (!list.length) box.appendChild(el('div', 'hint', hintText));
    card.appendChild(box);
    if (onPick) card.addEventListener('click', onPick);
    return card;
  }

  function render() {
    $('weekText').textContent = '第 ' + C.cnNum(state.week) + ' 周';
    var r = C.weekRange(state.week, state.cfg);
    $('weekRange').textContent = (r.start.getMonth() + 1) + '/' + r.start.getDate() + '（周六） → ' +
      (r.end.getMonth() + 1) + '/' + r.end.getDate() + '（周五） · 只影响表头日期';

    var list = $('days'); list.innerHTML = '';
    DAYS.forEach(function (wd) { list.appendChild(dayCard(wd)); });
    var trays = $('trays'); trays.innerHTML = '';
    trays.appendChild(trayCard('dates', '备用格', '放日期截图（通知转发那类）', state.dates,
      function () { openPicker('dates'); }));

    var filled = DAYS.filter(function (wd) { return state.chat[wd].length; }).length;
    var missing = DAYS.filter(function (wd) { return !state.chat[wd].length; });
    $('summary').textContent = '已归位 ' + filled + '/7 天 · 备用 ' + state.dates.length + ' 张' +
      (missing.length ? ' · 缺：' + missing.map(function (w) { return '周' + w; }).join('、') : '');

    $('inClass').value = state.cfg.className || '';
    $('inName').value = state.cfg.studentName || '';
    $('inMonday').value = state.cfg.firstWeekMonday || '';
    $('inCycle').value = state.cfg.cycleStartWeekday || 6;

    $('genBtn').disabled = state.busy || state.week === null;
    $('result').style.display = state.last ? 'block' : 'none';
    if (state.last) {
      $('resultText').textContent = '✅ ' + state.last.name + '（' + state.last.sizeKB + ' KB，' +
        state.last.images + ' 张图）' +
        (state.last.missing.length ? '\n还缺：' + state.last.missing.join('、') : '');
    }
  }

  // ───────── 生成 ─────────
  function generate() {
    if (state.busy) return;
    if (!state.cfg.className || !state.cfg.studentName) {       // #5
      $('settings').style.display = 'block';
      log('生成前请先在下面填好「班级」和「姓名」——表格里要用。');
      $('inClass').scrollIntoView({ behavior: 'smooth' });
      return;
    }
    state.busy = true;
    $('genBtn').disabled = true;
    setProgress(0, '准备中…');
    var t0 = Date.now();
    var total = DAYS.reduce(function (n, wd) { return n + state.chat[wd].length; }, 0) + state.dates.length;

    D.build({
      week: state.week,
      cfg: state.cfg,
      chat: (function () {
        var o = {};
        DAYS.forEach(function (wd) { o[wd] = state.chat[wd].map(function (s) { return s.file; }); });
        return o;
      })(),
      dates: state.dates.map(function (s) { return s.file; }),
      onProgress: function (m) {
        var m2 = /(\d+)\/(\d+)/.exec(m);
        setProgress(m2 ? (+m2[1] / Math.max(1, +m2[2])) : 0.3, m);
      }
    }).then(function (res) {
      state.last = res;
      state.busy = false;
      setProgress(1, '完成，用时 ' + ((Date.now() - t0) / 1000).toFixed(1) + ' 秒');
      log('生成完成。');
      render();
      saveToPhone(false);
    }).catch(function (e) {
      state.busy = false;
      setProgress(0, '');
      log('生成失败：' + (e && e.message ? e.message : e));
      render();
    });
  }

  function setProgress(p, text) {
    var box = $('progressBox');
    if (!text && !p) { box.style.display = 'none'; return; }
    box.style.display = 'block';
    $('progressBar').style.width = Math.round(Math.max(0, Math.min(1, p)) * 100) + '%';
    $('progressText').textContent = text || '';
  }

  function blobToBase64(blob) {
    return new Promise(function (resolve, reject) {
      var fr = new FileReader();
      fr.onload = function () {
        var s = String(fr.result);
        resolve(s.substring(s.indexOf(',') + 1));
      };
      fr.onerror = function () { reject(new Error('读取生成结果失败')); };
      fr.readAsDataURL(blob);
    });
  }

  function saveToPhone(share) {
    if (!state.last) { log('先生成一份吧。'); return; }
    if (!window.Daka) { log('这一版没接上壳，文档只在内存里。'); return; }
    log(share ? '正在准备分享…' : '正在保存到手机…');
    blobToBase64(state.last.blob).then(function (b64) {
      var r = share ? window.Daka.saveAndShare(b64, state.last.name)
                    : window.Daka.saveDocx(b64, state.last.name);
      log(r && r.indexOf('OK') === 0 ? (share ? '已发起分享。' : '已保存：' + r.substring(3)) : ('保存失败：' + r));
    }).catch(function (e) { log('保存失败：' + (e && e.message ? e.message : e)); });
  }

  function openLast() {
    if (!window.Daka) { log('这一版没接上壳。'); return; }
    if (!state.last) { log('先生成一份吧。'); return; }
    blobToBase64(state.last.blob).then(function (b64) {
      window.Daka.saveDocx(b64, state.last.name);     // 先确保文件在
      var r = window.Daka.openLast();
      log(r && r.indexOf('OK') === 0 ? '已交给办公软件打开。' : ('打开失败：' + r));
    }).catch(function (e) { log('打开失败：' + (e && e.message ? e.message : e)); });
  }

  // ───────── 绑定 ─────────
  function bind() {
    $('fileInput').addEventListener('change', function (e) { onFilesPicked(e.target.files); e.target.value = ''; });
    $('pickBtn').addEventListener('click', function () { openPicker('auto'); });
    $('prevWeek').addEventListener('click', function () {
      state.week = Math.max(1, (state.week || C.todayWeek(state.cfg)) - 1);
      persistAll().then(render);
    });
    $('nextWeek').addEventListener('click', function () {
      state.week = (state.week || C.todayWeek(state.cfg)) + 1;
      persistAll().then(render);
    });
    $('genBtn').addEventListener('click', generate);
    $('saveBtn').addEventListener('click', function () { saveToPhone(false); });
    $('shareBtn').addEventListener('click', function () { saveToPhone(true); });
    $('openBtn').addEventListener('click', openLast);
    $('preview').addEventListener('click', function () { closePreview(); });

    // #6 边输边存
    ['inClass', 'inName', 'inMonday', 'inCycle'].forEach(function (id) {
      $(id).addEventListener('input', function () {
        state.cfg.className = $('inClass').value.trim();
        state.cfg.studentName = $('inName').value.trim();
        state.cfg.firstWeekMonday = $('inMonday').value.trim() || C.DEFAULT_CFG.firstWeekMonday;
        state.cfg.cycleStartWeekday = +($('inCycle').value) || 6;
        saveCfg();
      });
      $(id).addEventListener('change', function () {
        persistAll().then(render);      // 改设置只影响表头日期，不动已归位的图
      });
    });

    $('settingsToggle').addEventListener('click', function () {
      var s = $('settings');
      s.style.display = s.style.display === 'none' ? 'block' : 'none';
    });
    $('clearBtn').addEventListener('click', function () {
      if (!confirm('清空所有已选的图？（班级姓名等设置会保留）')) return;
      DAYS.forEach(function (wd) { state.chat[wd] = []; });
      state.dates = []; state.last = null;
      IDB.clear().catch(function () { });
      log('已清空。');
      render();
    });

    window.addEventListener('popstate', function () {   // #18
      if ($('preview').style.display === 'flex') closePreview();
    });
  }

  function boot() {
    bind();
    if (state.week == null) state.week = C.todayWeek(state.cfg);   // 默认本周，之后你自己用 ◀ ▶ 调
    restore().then(function (ok) {
      if (ok) log('已恢复上次选的图（' + allShots().length + ' 张）。');
      if (!state.cfg.className || !state.cfg.studentName) {
        $('settings').style.display = 'block';
        log('先在下面把「班级」和「姓名」填上（只存在手机本地）。');
      }
      render();
    });
  }

  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', boot);
  else boot();
})();
