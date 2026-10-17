/* 在手机上本地生成 docx —— 不联网、不装任何库。
 * 做法：把模板的各个部件 + 新图片，自己按 ZIP 格式拼成一个 .docx（用 stored 不压缩）。
 * 图片用 canvas 转 JPEG，格子尺寸算法与电脑版 打卡核心.py 的 fit() 完全一致。
 * 挂在 window.DakaDocx 上。 */
(function () {
  'use strict';

  var W = 'http://schemas.openxmlformats.org/wordprocessingml/2006/main';
  var R_NS = 'http://schemas.openxmlformats.org/officeDocument/2006/relationships';
  var WP = 'http://schemas.openxmlformats.org/drawingml/2006/wordprocessingDrawing';
  var A_NS = 'http://schemas.openxmlformats.org/drawingml/2006/main';
  var PIC = 'http://schemas.openxmlformats.org/drawingml/2006/picture';
  var XMLNS = 'http://www.w3.org/XML/1998/namespace';

  var CM = 360000;                 // 1 厘米 = 360000 EMU
  var BOX_W_CM = 19.5, BOX_H_CM = 24.6;

  var LABEL_ROWS = { 六: 2, 日: 4, 一: 6, 二: 8, 三: 10, 四: 12, 五: 14 };
  var SLOT_ROWS = { 六: 3, 日: 5, 一: 7, 二: 9, 三: 11, 四: 13, 五: 15 };
  var SPARE_ROW = 18;
  var DAYS = ['六', '日', '一', '二', '三', '四', '五'];
  var WD_CN = { 六: '上周六', 日: '上周日', 一: '本周一', 二: '本周二', 三: '本周三', 四: '本周四', 五: '本周五' };

  // ───────── CRC32 + ZIP（stored） ─────────
  var CRC_TABLE = (function () {
    var t = new Uint32Array(256);
    for (var n = 0; n < 256; n++) {
      var c = n;
      for (var k = 0; k < 8; k++) c = (c & 1) ? (0xEDB88320 ^ (c >>> 1)) : (c >>> 1);
      t[n] = c >>> 0;
    }
    return t;
  })();

  function crc32(u8) {
    var c = 0xFFFFFFFF;
    for (var i = 0; i < u8.length; i++) c = CRC_TABLE[(c ^ u8[i]) & 0xFF] ^ (c >>> 8);
    return (c ^ 0xFFFFFFFF) >>> 0;
  }

  function utf8(str) { return new TextEncoder().encode(str); }

  function zipStore(entries) {
    var chunks = [], central = [], offset = 0;
    var enc = new TextEncoder();
    entries.forEach(function (e) {
      var nameBytes = enc.encode(e.name);
      var data = e.data instanceof Uint8Array ? e.data : utf8(String(e.data));
      var crc = crc32(data);
      var lh = new DataView(new ArrayBuffer(30));
      lh.setUint32(0, 0x04034b50, true);   // local file header
      lh.setUint16(4, 20, true);           // version
      lh.setUint16(6, 0x0800, true);       // UTF-8 文件名
      lh.setUint16(8, 0, true);            // stored
      lh.setUint16(10, 0, true);           // time
      lh.setUint16(12, 0x21, true);        // date（1980-01-01）
      lh.setUint32(14, crc, true);
      lh.setUint32(18, data.length, true);
      lh.setUint32(22, data.length, true);
      lh.setUint16(26, nameBytes.length, true);
      lh.setUint16(28, 0, true);
      chunks.push(new Uint8Array(lh.buffer), nameBytes, data);

      var ch = new DataView(new ArrayBuffer(46));
      ch.setUint32(0, 0x02014b50, true);   // central directory
      ch.setUint16(4, 20, true);
      ch.setUint16(6, 20, true);
      ch.setUint16(8, 0x0800, true);
      ch.setUint16(10, 0, true);
      ch.setUint16(12, 0, true);
      ch.setUint16(14, 0x21, true);
      ch.setUint32(16, crc, true);
      ch.setUint32(20, data.length, true);
      ch.setUint32(24, data.length, true);
      ch.setUint16(28, nameBytes.length, true);
      ch.setUint32(42, offset, true);
      central.push(new Uint8Array(ch.buffer), nameBytes);
      offset += 30 + nameBytes.length + data.length;
    });
    var cdSize = central.reduce(function (n, a) { return n + a.length; }, 0);
    var eocd = new DataView(new ArrayBuffer(22));
    eocd.setUint32(0, 0x06054b50, true);
    eocd.setUint16(8, entries.length, true);
    eocd.setUint16(10, entries.length, true);
    eocd.setUint32(12, cdSize, true);
    eocd.setUint32(16, offset, true);
    return new Blob(chunks.concat(central, [new Uint8Array(eocd.buffer)]),
      { type: 'application/vnd.openxmlformats-officedocument.wordprocessingml.document' });
  }

  // ───────── 图片 → JPEG ─────────
  function loadImageElement(file) {
    return new Promise(function (resolve, reject) {
      var url = URL.createObjectURL(file);
      var img = new Image();
      img.onload = function () { resolve({ img: img, url: url }); };
      img.onerror = function () { URL.revokeObjectURL(url); reject(new Error('这张图读不出来（格式可能不支持）：' + (file.name || ''))); };
      img.src = url;
    });
  }

  // 返回 { w, h, data(Uint8Array JPEG) }；w/h 是原始像素（跟电脑版一样，用原始比例算尺寸）
  function fileToJpeg(file, maxPx, quality) {
    maxPx = maxPx || 3000;
    quality = quality == null ? 0.85 : quality;
    return loadImageElement(file).then(function (o) {
      var img = o.img;
      var w = img.naturalWidth || img.width, h = img.naturalHeight || img.height;
      if (!w || !h) throw new Error('图片尺寸读不出来：' + (file.name || ''));
      var scale = Math.min(1, maxPx / Math.max(w, h));
      var cw = Math.max(1, Math.round(w * scale)), chh = Math.max(1, Math.round(h * scale));
      var canvas = document.createElement('canvas');
      canvas.width = cw; canvas.height = chh;
      var ctx = canvas.getContext('2d');
      ctx.fillStyle = '#fff';
      ctx.fillRect(0, 0, cw, chh);
      ctx.drawImage(img, 0, 0, cw, chh);
      URL.revokeObjectURL(o.url);
      return new Promise(function (resolve, reject) {
        canvas.toBlob(function (blob) {
          if (!blob) { reject(new Error('转 JPEG 失败：' + (file.name || ''))); return; }
          blob.arrayBuffer().then(function (buf) {
            resolve({ w: w, h: h, data: new Uint8Array(buf) });
          });
        }, 'image/jpeg', quality);
      });
    });
  }

  // 跟电脑版 fit() 一致：按比例缩到格子里
  function fit(iw, ih, bwCm, bhCm) {
    var bw = bwCm * CM, bh = bhCm * CM;
    if (!iw || !ih) return { cx: Math.round(bw), cy: Math.round(bh) };
    var k = Math.min(bw / iw, bh / ih);
    return { cx: Math.round(iw * k), cy: Math.round(ih * k) };
  }

  // 格子可用宽度（备用格只有 6cm 宽）：从 tcPr/tcW 里读，跟电脑版一样
  function cellBoxCm(tc, doc) {
    var pr = tc.getElementsByTagNameNS(W, 'tcPr');
    if (pr.length) {
      var wq = pr[0].getElementsByTagNameNS(W, 'tcW');
      if (wq.length && wq[0].getAttributeNS(W, 'type') === 'dxa') {
        return Math.max(2.0, parseInt(wq[0].getAttributeNS(W, 'w'), 10) / 567 - 0.4);
      }
    }
    return BOX_W_CM;
  }

  function drawingP(cx, cy, id) {
    return '<w:p xmlns:w="' + W + '" xmlns:r="' + R_NS + '" xmlns:wp="' + WP + '" xmlns:a="' + A_NS + '">' +
      '<w:pPr><w:jc w:val="center"/></w:pPr><w:r><w:drawing>' +
      '<wp:inline distT="0" distB="0" distL="114300" distR="114300">' +
      '<wp:extent cx="' + cx + '" cy="' + cy + '"/><wp:effectExtent l="0" t="0" r="0" b="0"/>' +
      '<wp:docPr id="' + id + '" name="图片 ' + id + '"/>' +
      '<wp:cNvGraphicFramePr><a:graphicFrameLocks noChangeAspect="1"/></wp:cNvGraphicFramePr>' +
      '<a:graphic><a:graphicData uri="' + PIC + '"><pic:pic xmlns:pic="' + PIC + '">' +
      '<pic:nvPicPr><pic:cNvPr id="' + id + '" name="图片 ' + id + '"/><pic:cNvPicPr><a:picLocks noChangeAspect="1"/></pic:cNvPicPr></pic:nvPicPr>' +
      '<pic:blipFill><a:blip r:embed="rId' + id + '"/><a:stretch><a:fillRect/></a:stretch></pic:blipFill>' +
      '<pic:spPr><a:xfrm><a:off x="0" y="0"/><a:ext cx="' + cx + '" cy="' + cy + '"/></a:xfrm>' +
      '<a:prstGeom prst="rect"><a:avLst/></a:prstGeom></pic:spPr>' +
      '</pic:pic></a:graphicData></a:graphic>' +
      '</wp:inline></w:drawing></w:r></w:p>';
  }

  function parseXml(text) {
    var d = new DOMParser().parseFromString(text, 'application/xml');
    if (d.getElementsByTagName('parsererror').length) throw new Error('XML 解析失败');
    return d;
  }

  function setRowLabel(row, text) {
    var ts = row.getElementsByTagNameNS(W, 't');
    if (!ts.length) return;
    ts[0].textContent = text;
    ts[0].setAttributeNS(XMLNS, 'xml:space', 'preserve');
    for (var i = 1; i < ts.length; i++) ts[i].textContent = '';
  }

  /* build(opts) -> Promise<{blob, name, images, missing}>
   * opts = { week, cfg, chat: {星期: [File]}, dates: [File], onProgress(msg) } */
  function build(opts) {
    var cfg = opts.cfg, week = opts.week;
    var C = window.DakaCore;
    var parts = {};
    var names = Object.keys(window.TEMPLATE || {});
    if (!names.length) return Promise.reject(new Error('模板没加载进来（template.js 缺失）'));
    names.forEach(function (n) { parts[n] = window.TEMPLATE[n]; });

    var doc = parseXml(parts['word/document.xml']);
    var body = doc.getElementsByTagNameNS(W, 'body')[0];
    var tbl = body.getElementsByTagNameNS(W, 'tr');   // 先拿行
    // 真正的表格元素
    var tblEl = body.getElementsByTagNameNS(W, 'tbl')[0];
    var rows = tblEl.getElementsByTagNameNS(W, 'tr');
    if (rows.length < 19) return Promise.reject(new Error('模板行数不对：' + rows.length));

    var relsText = parts['word/_rels/document.xml.rels'];
    var media = [];
    var images = 0, sizedDown = [];
    var nextId = 100;

    function addImage(tc, jpeg, maxHCm) {
      nextId++;
      var id = nextId;
      var boxW = cellBoxCm(tc, doc);
      var dim = fit(jpeg.w, jpeg.h, boxW, maxHCm);
      var mediaName = 'word/media/img' + id + '.jpeg';
      media.push({ name: mediaName, data: jpeg.data });
      relsText = relsText.replace('</Relationships>',
        '<Relationship Id="rId' + id + '" Type="' + R_NS + '/image" Target="media/img' + id + '.jpeg"/></Relationships>');
      var node = parseXml(drawingP(dim.cx, dim.cy, id)).documentElement;
      tc.appendChild(doc.importNode(node, true));
      images++;
    }

    // 一格里多张图 → 平分高度（跟电脑版一致）
    function putCell(tc, files, label) {
      if (!files || !files.length) return Promise.resolve();   // 没图也要返回 Promise，否则链会断
      var per = BOX_H_CM / files.length;
      if (files.length > 1) sizedDown.push(label + '（' + files.length + ' 张）');
      var chain = Promise.resolve();
      files.forEach(function (f) {
        chain = chain.then(function () {
          return fileToJpeg(f).then(function (jpeg) { addImage(tc, jpeg, per); });
        });
      });
      return chain;
    }

    var start = C.cycleStart(week, cfg);
    var missing = [];
    var chain = Promise.resolve();
    var total = 0;
    DAYS.forEach(function (wd) { total += (opts.chat[wd] || []).length; });
    var done = 0;

    DAYS.forEach(function (wd, i) {
      chain = chain.then(function () {
        var d = C.addDays(start, i);
        setRowLabel(rows[LABEL_ROWS[wd]], WD_CN[wd] + '（' + d.getDate() + '）');
        var tcs = rows[SLOT_ROWS[wd]].getElementsByTagNameNS(W, 'tc');
        if (tcs.length < 2) throw new Error('模板单元格异常（周' + wd + '）');
        var files = opts.chat[wd] || [];
        if (!files.length) missing.push('周' + wd);      // 措辞跟界面卡片一致
        return putCell(tcs[1], files, '周' + wd).then(function () {
          done += files.length;
          if (opts.onProgress) opts.onProgress('正在处理图片 ' + done + '/' + total + '…');
        });
      });
    });

    // 备用格：日期截图；超过 3 张就复制第 18 行往下加
    var dates = opts.dates || [];
    var spareRows = [rows[SPARE_ROW]];
    for (var k = 0; k < dates.length; k++) {
      (function (k) {
        chain = chain.then(function () {
          var rowNo = Math.floor(k / 3), slot = k % 3;
          if (rowNo >= spareRows.length) {
            var newRow = rows[SPARE_ROW].cloneNode(true);
            // 清掉新行里的图和文字，重编备用格编号
            var tcs = newRow.getElementsByTagNameNS(W, 'tc');
            for (var ci = 0; ci < tcs.length; ci++) {
              Array.prototype.slice.call(tcs[ci].getElementsByTagNameNS(W, 'p')).forEach(function (p) {
                if (p.getElementsByTagNameNS(W, 'drawing').length) tcs[ci].removeChild(p);
              });
              var ts = tcs[ci].getElementsByTagNameNS(W, 't');
              for (var ti = 0; ti < ts.length; ti++) ts[ti].textContent = '';
              if (ci > 0 && ts.length) ts[0].textContent = '备用格' + (rowNo * 3 + ci);
            }
            tblEl.appendChild(newRow);
            spareRows.push(newRow);
          }
          var tc = spareRows[rowNo].getElementsByTagNameNS(W, 'tc')[slot + 1];
          return putCell(tc, [dates[k]], '备用格' + (slot + 1));
        });
      })(k);
    }

    // 班级 / 姓名
    chain = chain.then(function () {
      var ts = doc.getElementsByTagNameNS(W, 't');
      for (var i = 0; i < ts.length; i++) {
        var t = ts[i];
        if (!t.textContent) continue;
        if (t.textContent.indexOf('填自己班') >= 0) t.textContent = cfg.className || '';
        if (t.textContent.indexOf('填自己名字') >= 0) t.textContent = cfg.studentName || '';
      }
    });

    return chain.then(function () {
      var ser = new XMLSerializer();
      var decl = '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\r\n';
      // 注意：Chromium 的 XMLSerializer 自己就会吐一个 <?xml ...?>，必须先剥掉再补我们的，
      // 否则会出现两个声明（invalid XML），Word/WPS 会认为文件损坏。
      var docStr = ser.serializeToString(doc).replace(/^\s*<\?xml[^>]*\?>\s*/, '');
      var relStr = relsText.replace(/^\s*<\?xml[^>]*\?>\s*/, '');
      parts['word/document.xml'] = decl + docStr;
      parts['word/_rels/document.xml.rels'] = decl + relStr;

      var entries = Object.keys(parts).map(function (n) {
        return { name: n, data: utf8(parts[n]) };
      });
      media.forEach(function (m) { entries.push({ name: m.name, data: m.data }); });

      var blob = zipStore(entries);
      var safe = String(cfg.className || '打卡表').replace(/[\\/:*?"<>|]/g, '');
      return {
        blob: blob,
        name: safe + '第' + C.cnNum(week) + '周打卡.docx',
        images: images,
        missing: missing,
        sizedDown: sizedDown,
        sizeKB: Math.round(blob.size / 1024)
      };
    });
  }

  window.DakaDocx = { build: build, zipStore: zipStore, crc32: crc32, fileToJpeg: fileToJpeg };
})();
