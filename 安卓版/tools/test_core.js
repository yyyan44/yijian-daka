// 核心逻辑自测（node 安卓版/tools/test_core.js）
// 对照值来自电脑版 Python：week1Start=2026-08-29、2026-10-09 属第 6 周
const fs = require('fs');
const path = require('path');

const src = fs.readFileSync(path.join(__dirname, '..', 'app', 'src', 'main', 'assets', 'core.js'), 'utf8');
global.window = {};
eval(src);
const C = global.window.DakaCore;

const cfg = { className: 'X', studentName: 'Y', firstWeekMonday: '2026-08-31', cycleStartWeekday: 6 };
let bad = 0;
function eq(label, got, want) {
  const ok = String(got) === String(want);
  if (!ok) bad++;
  console.log(`  ${ok ? 'OK  ' : 'FAIL'} ${label}: ${got}${ok ? '' : '  （应为 ' + want + '）'}`);
}

eq('第 1 周起点', C.ymd(C.week1Start(cfg)), '2026-08-29');
eq('2026-10-03 属第几周', C.weekOf(new Date(2026, 9, 3), cfg), 6);
eq('2026-10-09 属第几周', C.weekOf(new Date(2026, 9, 9), cfg), 6);
eq('2026-10-10 属第几周', C.weekOf(new Date(2026, 9, 10), cfg), 7);
eq('第 6 周周期', C.ymd(C.weekRange(6, cfg).start) + '~' + C.ymd(C.weekRange(6, cfg).end), '2026-10-03~2026-10-09');
eq('描述', C.describeWeek(6, cfg), '第六周 10/3（周六） → 10/9（周五）');
eq('认星期·周六_20261003', C.weekdayFromName('周六_20261003.png'), '六');
eq('认星期·第06周_周四_01', C.weekdayFromName('第06周_周四_01.png'), '四');
eq('认星期·礼拜3', C.weekdayFromName('礼拜3的截图.png'), '三');
eq('认星期·无关文件名', C.weekdayFromName('abc.png'), 'null');
eq('认日期·Screenshot 2026-10-09 222006', C.ymd(C.dateFromName('Screenshot 2026-10-09 222006.png')), '2026-10-09');
eq('认日期·20261003', C.ymd(C.dateFromName('x_20261003.png')), '2026-10-03');

const shots = [
  C.makeShot({ name: '周六_20261003.png', lastModified: 0 }, cfg),
  C.makeShot({ name: '周一_20261005.png', lastModified: 0 }, cfg),
  C.makeShot({ name: '周四_20261008.png', lastModified: 0 }, cfg)
];
const r = C.classify(shots);
eq('归位到周六', r.chat['六'].length, 1);
eq('归位到周一', r.chat['一'].length, 1);
eq('归位到周四', r.chat['四'].length, 1);
eq('其他天都是空的', ['日', '二', '三', '五'].every(w => r.chat[w].length === 0), true);

// 关键回归：下一周才做本周打卡（跨周）也要照样按星期几归位，不再被丢掉
const cross = [
  C.makeShot({ name: '周六_20261010.png', lastModified: 0 }, cfg),   // 第 7 周的周六
  C.makeShot({ name: '周日_20261011.png', lastModified: 0 }, cfg)
];
const r2 = C.classify(cross);
eq('跨周的周六照样进周六', r2.chat['六'].length, 1);
eq('跨周的周日照样进周日', r2.chat['日'].length, 1);
eq('没有未归位这种桶', r2.leftover, undefined);

console.log(bad ? `\n有 ${bad} 项不符` : '\n全部通过 ✅');
process.exit(bad ? 1 : 0);
