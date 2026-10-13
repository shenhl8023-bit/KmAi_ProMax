// 当前零件（左视口）：蓝灰色
export const CURRENT_PART_COLOR    = 0x4a7fc1;
// 候选零件（右视口）：紫色
export const CANDIDATE_PART_COLOR  = 0x7c4dbd;

export function modelColorForSlot(slot) {
  return slot === 'candidate' ? CANDIDATE_PART_COLOR : CURRENT_PART_COLOR;
}
