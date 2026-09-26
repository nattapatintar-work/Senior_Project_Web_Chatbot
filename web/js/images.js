/*
 * web/js/images.js
 * ================
 * Prepares a picked/pasted photo for upload:
 *   - decodes it (honouring EXIF rotation),
 *   - downscales so the longer side is <= 1600 px and re-encodes as JPEG when
 *     that helps (phone photos are often > 8 MB, the backend's hard limit;
 *     YOLO works at 640 px anyway),
 *   - leaves small, already-supported files untouched,
 *   - returns a Blob plus an object URL for the thumbnail.
 *
 * Failures reject with an Error whose `.code` is one of:
 *   not_image | undecodable | too_large
 */
(function (root) {
  "use strict";

  var FG = (root.FG = root.FG || {});
  var logic = FG.logic;

  function fail(code, message) {
    var e = new Error(message);
    e.code = code;
    return e;
  }

  var MESSAGES = {
    not_image: "ไฟล์นี้ไม่ใช่รูปภาพ",
    undecodable: "เปิดรูปนี้ไม่ได้ (รูปแบบไม่รองรับ เช่น HEIC) ลองบันทึกเป็น JPG ก่อน",
    too_large: "รูปใหญ่เกิน 8 MB แม้ย่อขนาดแล้ว ลองรูปอื่น",
  };

  async function decode(file) {
    if (typeof createImageBitmap === "function") {
      try {
        return await createImageBitmap(file, { imageOrientation: "from-image" });
      } catch (e) { /* fall through to <img> */ }
    }
    return new Promise(function (resolve, reject) {
      var url = URL.createObjectURL(file);
      var img = new Image();
      img.onload = function () { URL.revokeObjectURL(url); resolve(img); };
      img.onerror = function () { URL.revokeObjectURL(url); reject(new Error("decode")); };
      img.src = url;
    });
  }

  function toBlob(canvas, type, quality) {
    return new Promise(function (resolve) { canvas.toBlob(resolve, type, quality); });
  }

  /** @returns Promise<{blob, name, url, type}> */
  async function prepare(file) {
    if (!file || (file.type && !/^image\//i.test(file.type))) throw fail("not_image", MESSAGES.not_image);

    var supported = logic.ALLOWED_IMAGE_TYPES.indexOf(file.type) !== -1;
    var bitmap;
    try {
      bitmap = await decode(file);
    } catch (e) {
      throw fail("undecodable", MESSAGES.undecodable);
    }
    var w = bitmap.width || bitmap.naturalWidth;
    var h = bitmap.height || bitmap.naturalHeight;
    var fit = logic.fitWithin(w, h, logic.MAX_IMAGE_SIDE);

    var blob = file;
    var name = file.name || "photo.jpg";
    if (!supported || fit.scaled || file.size > logic.KEEP_ORIGINAL_BELOW_BYTES) {
      var canvas = document.createElement("canvas");
      canvas.width = fit.width;
      canvas.height = fit.height;
      var ctx = canvas.getContext("2d");
      ctx.fillStyle = "#ffffff"; // transparent PNGs would otherwise turn black in JPEG
      ctx.fillRect(0, 0, fit.width, fit.height);
      ctx.drawImage(bitmap, 0, 0, fit.width, fit.height);
      if (bitmap.close) bitmap.close();
      blob = await toBlob(canvas, "image/jpeg", 0.85);
      if (!blob) throw fail("undecodable", MESSAGES.undecodable);
      name = logic.jpegName(name);
    } else if (bitmap.close) {
      bitmap.close();
    }

    if (blob.size > logic.MAX_IMAGE_BYTES) throw fail("too_large", MESSAGES.too_large);
    return { blob: blob, name: name, url: URL.createObjectURL(blob), type: blob.type };
  }

  FG.images = { prepare: prepare, MESSAGES: MESSAGES };
})(typeof window !== "undefined" ? window : globalThis);
