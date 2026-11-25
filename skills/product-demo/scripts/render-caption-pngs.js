// render-caption-pngs.js  -- macOS JXA (osascript -l JavaScript), no installs needed.
// usage: osascript -l JavaScript render-caption-pngs.js SPEC.json
// SPEC: {"width":1920,"height":1080,"font_px":84,"bottom_px":110,"max_width_frac":0.8,
//        "items":[{"text":"Click export","file":"/abs/path/c0001.png"}, ...]}
// Each PNG is a full-frame transparent RGBA image with the caption centred near the bottom
// on a translucent rounded box. An item with empty text produces a fully transparent frame.
ObjC.import('AppKit');
ObjC.import('Foundation');

function run(argv) {
  const specPath = argv[0];
  const data = $.NSString.stringWithContentsOfFileEncodingError(specPath, $.NSUTF8StringEncoding, null);
  const spec = JSON.parse(ObjC.unwrap(data));
  const W = spec.width, H = spec.height;
  const fontPx = spec.font_px || Math.round(H * 0.078);
  const bottom = spec.bottom_px || Math.round(H * 0.10);
  const maxW = Math.round(W * (spec.max_width_frac || 0.8));
  const padX = Math.round(fontPx * 0.45), padY = Math.round(fontPx * 0.22);
  const font = $.NSFont.boldSystemFontOfSize(fontPx);
  const para = $.NSMutableParagraphStyle.alloc.init;
  para.alignment = $.NSTextAlignmentCenter;
  para.lineBreakMode = $.NSLineBreakByWordWrapping;
  const attrs = $.NSMutableDictionary.alloc.init;
  attrs.setObjectForKey(font, $.NSFontAttributeName);
  attrs.setObjectForKey($.NSColor.whiteColor, $.NSForegroundColorAttributeName);
  attrs.setObjectForKey(para, $.NSParagraphStyleAttributeName);
  const boxColor = $.NSColor.colorWithSRGBRedGreenBlueAlpha(0, 0, 0, spec.box_alpha === undefined ? 0.62 : spec.box_alpha);

  let n = 0;
  for (const it of spec.items) {
    const rep = $.NSBitmapImageRep.alloc.initWithBitmapDataPlanesPixelsWidePixelsHighBitsPerSampleSamplesPerPixelHasAlphaIsPlanarColorSpaceNameBytesPerRowBitsPerPixel(
      null, W, H, 8, 4, true, false, $.NSDeviceRGBColorSpace, 0, 0);
    const ctx = $.NSGraphicsContext.graphicsContextWithBitmapImageRep(rep);
    $.NSGraphicsContext.saveGraphicsState;
    $.NSGraphicsContext.setCurrentContext(ctx);
    if (it.text && it.text.length) {
      const s = $.NSString.stringWithString(it.text);
      const opts = $.NSStringDrawingUsesLineFragmentOrigin | $.NSStringDrawingUsesFontLeading;
      const br = s.boundingRectWithSizeOptionsAttributes($.NSMakeSize(maxW, 10000), opts, attrs);
      const tw = Math.ceil(br.size.width), th = Math.ceil(br.size.height);
      const bw = tw + 2 * padX, bh = th + 2 * padY;
      const bx = Math.round((W - bw) / 2), by = bottom; // AppKit origin is bottom-left
      boxColor.setFill;
      $.NSBezierPath.bezierPathWithRoundedRectXRadiusYRadius($.NSMakeRect(bx, by, bw, bh), fontPx * 0.28, fontPx * 0.28).fill;
      s.drawWithRectOptionsAttributes($.NSMakeRect(Math.round((W - tw) / 2), by + padY, tw, th), opts, attrs);
    }
    ctx.flushGraphics;
    $.NSGraphicsContext.restoreGraphicsState;
    const png = rep.representationUsingTypeProperties($.NSBitmapImageFileTypePNG, $());
    png.writeToFileAtomically(it.file, true);
    n++;
  }
  return 'rendered ' + n + ' png(s)';
}
