(function attachXlsxWriter(root, factory) {
  const api = factory();
  if (typeof module === "object" && module.exports) module.exports = api;
  root.OverleafCommentsXlsx = api;
})(typeof globalThis !== "undefined" ? globalThis : this, function createXlsx() {
  "use strict";

  // A minimal .xlsx writer.
  //
  // An xlsx is a ZIP holding a few XML files. ZIP allows entries to be stored
  // uncompressed, so no DEFLATE is needed, which is what makes this small
  // enough to hand-roll. The alternative was bundling a spreadsheet library of
  // several hundred kilobytes into a thirty kilobyte extension, having told
  // the Chrome reviewers there is no remote code in it.
  //
  // Rows come from the same shape sheets.py builds in Python, so the two
  // exports can be compared on their data rather than on their bytes.

  const CRC_TABLE = (() => {
    const table = new Uint32Array(256);
    for (let i = 0; i < 256; i += 1) {
      let c = i;
      for (let k = 0; k < 8; k += 1) c = c & 1 ? 0xedb88320 ^ (c >>> 1) : c >>> 1;
      table[i] = c >>> 0;
    }
    return table;
  })();

  function crc32(bytes) {
    let c = 0xffffffff;
    for (let i = 0; i < bytes.length; i += 1) {
      c = CRC_TABLE[(c ^ bytes[i]) & 0xff] ^ (c >>> 8);
    }
    return (c ^ 0xffffffff) >>> 0;
  }

  const encoder = new TextEncoder();

  function zip(files) {
    // Stored entries only. Every field below is little-endian, as the format
    // specifies.
    const chunks = [];
    const central = [];
    let offset = 0;

    for (const { name, text } of files) {
      const nameBytes = encoder.encode(name);
      const data = encoder.encode(text);
      const sum = crc32(data);

      const local = new Uint8Array(30 + nameBytes.length);
      const lv = new DataView(local.buffer);
      lv.setUint32(0, 0x04034b50, true);      // local file header
      lv.setUint16(4, 20, true);              // version needed
      lv.setUint16(6, 0x0800, true);          // names are UTF-8
      lv.setUint16(8, 0, true);               // stored, not deflated
      lv.setUint32(14, sum, true);
      lv.setUint32(18, data.length, true);
      lv.setUint32(22, data.length, true);
      lv.setUint16(26, nameBytes.length, true);
      local.set(nameBytes, 30);
      chunks.push(local, data);

      const entry = new Uint8Array(46 + nameBytes.length);
      const cv = new DataView(entry.buffer);
      cv.setUint32(0, 0x02014b50, true);      // central directory header
      cv.setUint16(4, 20, true);
      cv.setUint16(6, 20, true);
      cv.setUint16(8, 0x0800, true);
      cv.setUint16(10, 0, true);
      cv.setUint32(16, sum, true);
      cv.setUint32(20, data.length, true);
      cv.setUint32(24, data.length, true);
      cv.setUint16(28, nameBytes.length, true);
      cv.setUint32(42, offset, true);
      entry.set(nameBytes, 46);
      central.push(entry);

      offset += local.length + data.length;
    }

    const centralSize = central.reduce((n, e) => n + e.length, 0);
    const end = new Uint8Array(22);
    const ev = new DataView(end.buffer);
    ev.setUint32(0, 0x06054b50, true);        // end of central directory
    ev.setUint16(8, files.length, true);
    ev.setUint16(10, files.length, true);
    ev.setUint32(12, centralSize, true);
    ev.setUint32(16, offset, true);

    const total = chunks.reduce((n, c) => n + c.length, 0) + centralSize + 22;
    const out = new Uint8Array(total);
    let at = 0;
    for (const part of [...chunks, ...central, end]) {
      out.set(part, at);
      at += part.length;
    }
    return out;
  }

  // Control characters are not legal in XML and Excel refuses the whole file
  // rather than skipping them. Pasted comment text really does contain them.
  const ILLEGAL = new RegExp("[\\u0000-\\u0008\\u000B\\u000C\\u000E-\\u001F]", "g");

  function xmlEscape(value) {
    return String(value)
      .replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;").replace(/'/g, "&apos;")
      .replace(ILLEGAL, "");
  }

  function columnName(index) {
    let name = "";
    let n = index;
    while (n > 0) {
      const rem = (n - 1) % 26;
      name = String.fromCharCode(65 + rem) + name;
      n = Math.floor((n - 1) / 26);
    }
    return name;
  }

  function sheetXml(rows) {
    const body = rows.map((row, r) => {
      const cells = row.map((value, c) => {
        const ref = `${columnName(c + 1)}${r + 1}`;
        if (typeof value === "number" && Number.isFinite(value)) {
          return `<c r="${ref}"><v>${value}</v></c>`;
        }
        const text = value === null || value === undefined ? "" : String(value);
        if (!text) return "";
        // Inline strings, so there is no shared string table to keep in step.
        return `<c r="${ref}" t="inlineStr"><is><t xml:space="preserve">${xmlEscape(text)}</t></is></c>`;
      }).join("");
      return `<row r="${r + 1}">${cells}</row>`;
    }).join("");
    return '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
      + '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
      + `<sheetData>${body}</sheetData></worksheet>`;
  }

  function build(sheets) {
    const names = Object.keys(sheets);
    const files = [
      {
        name: "[Content_Types].xml",
        text: '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
          + '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
          + '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
          + '<Default Extension="xml" ContentType="application/xml"/>'
          + '<Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>'
          + names.map((_, i) => `<Override PartName="/xl/worksheets/sheet${i + 1}.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>`).join("")
          + "</Types>",
      },
      {
        name: "_rels/.rels",
        text: '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
          + '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
          + '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/>'
          + "</Relationships>",
      },
      {
        name: "xl/workbook.xml",
        text: '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
          + '<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"><sheets>'
          + names.map((name, i) => `<sheet name="${xmlEscape(name)}" sheetId="${i + 1}" r:id="rId${i + 1}"/>`).join("")
          + "</sheets></workbook>",
      },
      {
        name: "xl/_rels/workbook.xml.rels",
        text: '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
          + '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
          + names.map((_, i) => `<Relationship Id="rId${i + 1}" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet${i + 1}.xml"/>`).join("")
          + "</Relationships>",
      },
    ];
    names.forEach((name, i) => {
      files.push({ name: `xl/worksheets/sheet${i + 1}.xml`, text: sheetXml(sheets[name]) });
    });
    return zip(files);
  }

  return { build, crc32, columnName, xmlEscape };
});
