/**
 * 解析 RFC 4180 风格 CSV，支持引号、双引号转义和 CRLF。
 * Args:
 *   input: CSV 原始文本。
 * Returns:
 *   string[][]: 按行列拆分后的单元格。
 */
export const parseCsvRows = (input: string): string[][] => {
  const rows: string[][] = []
  let row: string[] = []
  let cell = ''
  let quoted = false
  const text = input.replace(/^\uFEFF/, '')

  for (let index = 0; index < text.length; index += 1) {
    const character = text[index]
    const next = text[index + 1]
    if (character === '"') {
      if (quoted && next === '"') {
        cell += '"'
        index += 1
      } else {
        quoted = !quoted
      }
      continue
    }
    if (character === ',' && !quoted) {
      row.push(cell)
      cell = ''
      continue
    }
    if ((character === '\n' || character === '\r') && !quoted) {
      if (character === '\r' && next === '\n') index += 1
      row.push(cell)
      if (row.some((value) => value.trim())) rows.push(row)
      row = []
      cell = ''
      continue
    }
    cell += character
  }
  if (quoted) throw new Error('CSV 存在未闭合的引号')
  row.push(cell)
  if (row.some((value) => value.trim())) rows.push(row)
  return rows
}
