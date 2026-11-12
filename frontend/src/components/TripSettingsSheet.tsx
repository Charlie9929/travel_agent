import { Archive, LogOut, Trash2 } from "lucide-react";
import { ModalSheet } from "./ModalSheet";

export function TripSettingsSheet({
  tripTitle,
  isOwner,
  archived,
  loading,
  onArchive,
  onDelete,
  onLeave,
  onClose,
}: {
  tripTitle: string;
  isOwner: boolean;
  archived: boolean;
  loading: boolean;
  onArchive: () => void;
  onDelete: () => void;
  onLeave: () => void;
  onClose: () => void;
}) {
  return (
    <ModalSheet title="旅行设置" onClose={onClose}>
      <p className="sheet-intro">管理「{tripTitle}」的生命周期和成员关系。</p>
      <div className="settings-actions">
        {isOwner ? <>
          <button className="settings-action" onClick={onArchive} disabled={loading || archived}>
            <Archive size={20} />
            <span>
              <strong>{archived ? "旅行已归档" : "结束并归档旅行"}</strong>
              <small>{archived ? "旅行记录会继续保留" : "保留行程记录，结束本次旅行"}</small>
            </span>
          </button>
          <button className="settings-action is-danger" onClick={onDelete} disabled={loading}>
            <Trash2 size={20} />
            <span>
              <strong>删除旅行</strong>
              <small>删除后将无法恢复，请谨慎操作</small>
            </span>
          </button>
        </> : <button className="settings-action is-danger" onClick={onLeave} disabled={loading}>
          <LogOut size={20} />
          <span>
            <strong>退出旅行</strong>
            <small>退出后不再看到这场旅行的内容</small>
          </span>
        </button>}
      </div>
    </ModalSheet>
  );
}
