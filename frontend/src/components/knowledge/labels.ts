export const ENTITY_TYPE_LABELS: Record<string, string> = {
  person: "人物",
  organization: "机构",
  place: "地点",
  role: "职衔",
  other: "其他",
};

export const DISAMBIGUATION_LABELS: Record<string, string> = {
  unresolved: "未消歧",
  candidate: "候选",
  confirmed: "已确认",
  split_required: "需拆分",
};

export const EVENT_TYPE_LABELS: Record<string, string> = {
  consultation: "会商",
  request: "请求",
  instruction: "指示",
  report: "报告",
  appointment: "任命",
  voyage: "航行",
  trade: "贸易",
  conflict: "冲突",
  correspondence: "通信",
  resolution: "决议",
  other: "其他",
};

export const CERTAINTY_LABELS: Record<string, string> = {
  certain: "确定",
  probable: "很可能",
  possible: "可能",
  uncertain: "不确定",
};

export const PREDICATE_LABELS: Record<string, string> = {
  appointed_to_role: "被任命为",
  held_role: "担任",
  communication_participation: "参与通信",
  directed_action: "指示行动",
  event_participation: "参与事件",
  represented_org: "代表机构",
  other: "其他",
};

export function label(map: Record<string, string>, key: string | undefined | null): string {
  if (!key) return "-";
  return map[key] || key;
}
