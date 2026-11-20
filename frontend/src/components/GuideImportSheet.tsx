import { useState } from "react";
import { ImagePlus, X } from "lucide-react";
import { ModalSheet } from "./ModalSheet";

const MAX_IMAGE_BYTES = 5 * 1024 * 1024;

export function GuideImportSheet({
  loading,
  onRecognize,
  onSubmit,
  onClose,
}: {
  loading: boolean;
  onRecognize: (file: File) => Promise<string>;
  onSubmit: (text: string) => void;
  onClose: () => void;
}) {
  const [text, setText] = useState("");
  const [images, setImages] = useState<File[]>([]);
  const [recognizing, setRecognizing] = useState(false);
  const [progress, setProgress] = useState("");
  const [error, setError] = useState("");

  const addImages = (files: FileList | null) => {
    if (!files) return;
    const accepted: File[] = [];
    for (const file of Array.from(files)) {
      if (!["image/jpeg", "image/png"].includes(file.type)) {
        setError("攻略截图仅支持 JPEG 和 PNG 图片");
        continue;
      }
      if (file.size > MAX_IMAGE_BYTES) {
        setError(`“${file.name}”超过 5MB，无法识别`);
        continue;
      }
      accepted.push(file);
    }
    setImages((current) => [...current, ...accepted].slice(0, 9));
  };

  const recognizeImages = async () => {
    if (!images.length) return;
    setRecognizing(true);
    setError("");
    try {
      const extracted: string[] = [];
      for (const [index, image] of images.entries()) {
        setProgress(`正在识别第 ${index + 1}/${images.length} 张截图…`);
        extracted.push(await onRecognize(image));
      }
      setText((current) => [current.trim(), ...extracted].filter(Boolean).join("\n\n"));
      setImages([]);
      setProgress("识别完成，请检查并修改文字后再提取候选活动");
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "截图识别失败");
      setProgress("");
    } finally {
      setRecognizing(false);
    }
  };

  return (
    <ModalSheet title="导入攻略" onClose={onClose} wide>
      <form className="auth-form" onSubmit={(event) => { event.preventDefault(); onSubmit(text.trim()); }}>
        <section className="guide-image-import">
          <div><strong>攻略截图</strong><small>最多选择 9 张 JPEG/PNG 图片，单张不超过 5MB</small></div>
          <label className="secondary-button guide-image-picker"><ImagePlus size={17} />选择截图<input type="file" accept="image/jpeg,image/png" multiple onChange={(event) => { addImages(event.target.files); event.currentTarget.value = ""; }} /></label>
          {!!images.length && <div className="guide-image-list">{images.map((image, index) => <span key={`${image.name}-${index}`}>{image.name}<button type="button" aria-label={`移除 ${image.name}`} onClick={() => setImages((current) => current.filter((_, itemIndex) => itemIndex !== index))}><X size={13} /></button></span>)}</div>}
          {!!images.length && <button type="button" className="secondary-button full-button" disabled={recognizing || loading} onClick={() => void recognizeImages()}>{recognizing ? progress : `识别 ${images.length} 张截图`}</button>}
          {progress && !recognizing && <small className="guide-ocr-status">{progress}</small>}
          {error && <p className="form-error">{error}</p>}
        </section>
        <label className="field-label">攻略文字<textarea className="text-area guide-text-area" value={text} onChange={(event) => setText(event.target.value)} placeholder="也可以直接粘贴攻略文字；截图识别完成后，请先校对地点、时间和价格。" /></label>
        <button className="primary-button full-button" disabled={loading || recognizing || !text.trim()}>{loading ? "正在提取候选活动…" : "提取候选活动"}</button>
      </form>
    </ModalSheet>
  );
}
