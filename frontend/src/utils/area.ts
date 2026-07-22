const MU_PER_HECTARE = 15

/**
 * 将公顷转换为亩。
 * Args:
 *   areaHa: 公顷面积。
 * Returns:
 *   number: 对应亩数。
 */
export const hectaresToMu = (areaHa: number): number => areaHa * MU_PER_HECTARE

/**
 * 格式化面积数值，空值返回占位符。
 * Args:
 *   area: 待格式化面积。
 *   fractionDigits: 保留小数位数。
 * Returns:
 *   string: 格式化结果或占位符。
 */
export const formatArea = (
  area: number | null | undefined,
  fractionDigits: number = 2,
): string => (
  typeof area === 'number' ? area.toFixed(fractionDigits) : '--'
)
