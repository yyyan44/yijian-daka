/* 打卡核心逻辑 —— 从电脑版 打卡核心.py 一比一移植，保证两边算出来一样。
 * 只做纯计算：周次推算、日期识别、按星期几归位。
 * 依赖：无。挂在 window.DakaCore 上。 */
(function () {
  'use strict';

  var DAYS = ['六', '日', '一', '二', '三', '四', '五'];
  var WD_CN = { 六: '上周六', 日: '上周日', 一: '本周一', 二: '本周二', 三: '本周三', 四: '本周四', 五: '本周五' };
  var WD_RANK = { 一: 1, 二: 2, 三: 3, 四: 4, 五: 5, 六: 6, 日: 7, 天: 7, '1': 1, '2': 2, '3': 3, '4': 4, '5': 5, '6': 6, '7': 7 };
  var RANK_WD = { 1: '一', 2: '二', 3: '三', 4: '四', 5: '五', 6: '六', 7: '日' };
  var CN_NUM = '零一二三四五六七八九';

  var DEFAULT_CFG = {
    className: '',
    studentName: '',
    firstWeekMonday: '2026-08-31',   // 第 1 周里的那个周一
    cycleStartWeekday: 6             // 一个周期从星期几起算：1=周一 … 6=周六
  };

  function cnNum(n) {
    n = Math.round(n);
    if (n < 10) return CN_NUM[n] || String(n);
    if (n === 10) return '十';
    if (n < 20) return '十' + CN_NUM[n % 10];
    return CN_NUM[Math.floor(n / 10)] + '十' + (n % 10 ? CN_NUM[n % 10] : '');
  }

  function parseYMD(s) {
    var m = /(\d{4})\D(\d{1,2})\D(\d{1,2})/.exec(String(s || ''));
    if (!m) return null;
    var d = new Date(+m[1], +m[2] - 1, +m[3]);
    return isNaN(d.getTime()) ? null : d;
  }

  function ymd(d) {
    var m = d.getMonth() + 1, day = d.getDate();
    return d.getFullYear() + '-' + (m < 10 ? '0' : '') + m + '-' + (day < 10 ? '0' : '') + day;
  }

  function addDays(d, n) {
    return new Date(d.getFullYear(), d.getMonth(), d.getDate() + n);
  }

  function today() {
    var n = new Date();
    return new Date(n.getFullYear(), n.getMonth(), n.getDate());
  }

  // 周一=1 … 周日=7
  function isoweekday(d) { return ((d.getDay() + 6) % 7) + 1; }

  function anchorMonday(cfg) {
    return parseYMD((cfg || DEFAULT_CFG).firstWeekMonday) || parseYMD(DEFAULT_CFG.firstWeekMonday);
  }

  // 第 1 周的起点（可能不是周一，看周期从哪天起算）
  function week1Start(cfg) {
    var a = anchorMonday(cfg);
    var startWd = +((cfg || DEFAULT_CFG).cycleStartWeekday || 6);
    var delta = (isoweekday(a) - startWd + 7) % 7;
    return addDays(a, -delta);
  }

  function cycleStart(week, cfg) { return addDays(week1Start(cfg), 7 * (week - 1)); }

  function weekRange(week, cfg) {
    var s = cycleStart(week, cfg);
    return { start: s, end: addDays(s, 6) };
  }

  function weekOf(d, cfg) {
    return Math.floor((d - week1Start(cfg)) / 86400000 / 7) + 1;
  }

  function todayWeek(cfg) { return weekOf(today(), cfg); }

  var WD_RE = /(?:周|星期|礼拜)\s*([一二三四五六日天1-7])/;

  function weekdayFromName(name) {
    var m = WD_RE.exec(String(name || ''));
    if (!m) return null;
    return RANK_WD[WD_RANK[m[1]]] || null;
  }

  // 文件名里的时间戳：20261009 / 2026-10-09 / 2026_10_09 222006
  var TS_RE = /(20\d{2})[-_.]?(0[1-9]|1[0-2])[-_.]?(0[1-9]|[12]\d|3[01])(?:[-_.\sT]?([01]\d|2[0-3])[-_.:]?([0-5]\d)[-_.:]?([0-5]\d))?/;

  function dateFromName(name) {
    var m = TS_RE.exec(String(name || ''));
    if (!m) return null;
    var d = new Date(+m[1], +m[2] - 1, +m[3]);
    return isNaN(d.getTime()) ? null : d;
  }

  // 这张图是哪天的：先认文件名，认不出用文件时间
  function shotDate(file) {
    var d = dateFromName(file.name || '');
    if (d) return { date: d, how: '文件名' };
    if (file.lastModified) return { date: new Date(file.lastModified), how: '文件时间' };
    return { date: today(), how: '系统日期' };
  }

  // 一张图 → 归位所需的全部信息
  function makeShot(file, cfg) {
    var sd = shotDate(file);
    var named = weekdayFromName(file.name || '');
    var weekday = named || RANK_WD[isoweekday(sd.date)];
    return {
      file: file,
      name: file.name || '(无名)',
      date: sd.date,
      how: sd.how,
      fromName: !!named,
      weekday: weekday,
      week: weekOf(sd.date, cfg || DEFAULT_CFG)
    };
  }

  // 按星期几归位 —— 只看「周几」，跟这张图是哪一周拍的没关系。
  // （做一周打卡经常在下一周周末才补，所以不能拿截图日期去推周次）
  function classify(shots) {
    var chat = {};
    DAYS.forEach(function (wd) { chat[wd] = []; });
    shots.forEach(function (s) { chat[s.weekday].push(s); });
    return { chat: chat };
  }

  function describeWeek(week, cfg) {
    var r = weekRange(week, cfg);
    return '第' + cnNum(week) + '周 ' +
      (r.start.getMonth() + 1) + '/' + r.start.getDate() + '（周六） → ' +
      (r.end.getMonth() + 1) + '/' + r.end.getDate() + '（周五）';
  }

  window.DakaCore = {
    DAYS: DAYS, WD_CN: WD_CN, RANK_WD: RANK_WD, DEFAULT_CFG: DEFAULT_CFG,
    cnNum: cnNum, ymd: ymd, parseYMD: parseYMD, addDays: addDays, today: today,
    isoweekday: isoweekday, week1Start: week1Start, cycleStart: cycleStart,
    weekRange: weekRange, weekOf: weekOf, todayWeek: todayWeek,
    weekdayFromName: weekdayFromName, dateFromName: dateFromName,
    shotDate: shotDate, makeShot: makeShot, classify: classify,
    describeWeek: describeWeek
  };
})();
