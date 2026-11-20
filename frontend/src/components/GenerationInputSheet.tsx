import { useState } from "react";
import { ImagePlus, X } from "lucide-react";
import { ModalSheet } from "./ModalSheet";
import { ProcessingSteps } from "./ProcessingSteps";

const MAX_IMAGE_BYTES = 5 * 1024 * 1024;

export function GenerationInputSheet({
  questions,
  loading,
  processingSteps,
  processingStep,
  onRecognize,
  onSubmit,
  onClose,
}: {
  questions: string[];
  loading: boolean;
  processingSteps: string[];
  processingStep: number;
  onRecognize: (file: File) => Promise<string>;
  onSubmit: (answer: string, guideText: string) => void;
  onClose: () => void;
}) {
  const [answer, setAnswer] = useState("");
  const [guideText, setGuideText] = useState("");
  const [images, setImages] = useState<File[]>([]);
  const [recognizing, setRecognizing] = useState(false);
  const [error, setError] = useState("");

  const addImages = (files: FileList | null) => {
    if (!files) return;
    const accepted = Array.from(files).filter((file) => {
      if (!["image/jpeg", "image/png"].includes(file.type)) { setError("攻略截图仅支持 JPEG 和 PNG 图片"); return false; }
      if (file.size > MAX_IMAGE_BYTES) { setError(`“${file.name}”超过 5MB`); return false; }
      return true;
    });
    setImages((current) => [...current, ...accepted].slice(0, 9));
  };

  const recognize = async () => {
    setRecognizing(true);
    setError("");
    try {
      const texts: string[] = [];
      for (const image of images) texts.push(await onRecognize(image));
      setGuideText((current) => [current.trim(), ...texts].filter(Boolean).join("\n\n"));
      setImages([]);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "截图识别失败");
    } finally {
      setRecognizing(false);
    }
  };

  return <ModalSheet title={questions.length ? "Agent 还需要确认" : "告诉 Agent 旅行偏好"} onClose={onClose} wide>
    <form className="auth-form" onSubmit={(event) => { event.preventDefault(); onSubmit(answer.trim(), guideText.trim()); }}>
      <label className="field-label">{questions.length ? questions.map((item, index) => `${index + 1}. ${item}`).join("\n") : "偏好、饮食和行动限制"}
        <textarea className="text-area" value={answer} onChange={(event) => setAnswer(event.target.value)} placeholder={questions.length ? "逐项回答；不限制可以填写“不限”" : "例如：节奏轻松、喜欢博物馆和川菜、有人膝盖不便；也可以只上传攻略"} required={Boolean(questions.length)} />
      </label>
      {!questions.length && <section className="guide-image-import">
        <div><strong>攻略参考（可选）</strong><small>上传截图或粘贴文字，Agent 会筛选其中适合本次日期、预算和路线的内容，不会机械照搬。</small></div>
        <label className="secondary-button guide-image-picker"><ImagePlus size={17} />选择攻略截图<input type="file" accept="image/jpeg,image/png" multiple onChange={(event) => { addImages(event.target.files); event.currentTarget.value = ""; }} /></label>
        {!!images.length && <div className="guide-image-list">{images.map((image, index) => <span key={`${image.name}-${index}`}>{image.name}<button type="button" onClick={() => setImages((current) => current.filter((_, itemIndex) => itemIndex !== index))}><X size={13} /></button></span>)}</div>}
        {!!images.length && <button type="button" className="secondary-button full-button" disabled={recognizing || loading} onClick={() => void recognize()}>{recognizing ? "正在识别截图…" : `识别 ${images.length} 张截图`}</button>}
        <textarea className="text-area guide-text-area" value={guideText} onChange={(event) => setGuideText(event.target.value)} placeholder="也可以直接粘贴攻略文字；识别后可在这里校对。" />
        {error && <p className="form-error">{error}</p>}
      </section>}
      {loading && <ProcessingSteps steps={processingSteps} activeStep={processingStep} />}
      <button className="primary-button full-button" disabled={loading || recognizing || (questions.length ? !answer.trim() : !answer.trim() && !guideText.trim())}>{questions.length ? "回答并继续" : "让 Agent 理解需求并生成"}</button>
    </form>
  </ModalSheet>;
}
