BEGIN;

ALTER TABLE imagery_processing_steps
    ADD COLUMN IF NOT EXISTS is_required BOOLEAN NOT NULL DEFAULT TRUE;

UPDATE imagery_processing_steps
SET sequence = 6
WHERE step_code = 'band_products'
  AND sequence = 5;

INSERT INTO imagery_processing_steps (
    asset_id,
    step_code,
    step_name,
    sequence,
    is_required,
    status,
    progress,
    parameters
)
SELECT
    asset.id,
    'enhancement',
    '影像增强',
    5,
    FALSE,
    'pending',
    0,
    '{"method": "optional"}'::jsonb
FROM imagery_assets AS asset
WHERE NOT EXISTS (
    SELECT 1
    FROM imagery_processing_steps AS step
    WHERE step.asset_id = asset.id
      AND step.step_code = 'enhancement'
);

COMMIT;
