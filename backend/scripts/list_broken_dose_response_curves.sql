-- Read-only: dose-response curves that cannot fit as intended, one row per curve.
--
-- Same rules the protocol enforces on create, publish and edit since the curve guards:
--   * the Y readout exists on the protocol and is numeric
--   * the X readout (when set) exists, or is a well-metadata name such as "concentration"
--   * a chosen Y layer is one the Y readout calculates
--   * a Y layer is chosen when the Y readout calculates two or more
-- Protocols stored before the guards still load; fix each listed curve with
-- "New Version" (published) or by editing the curve (draft).
--
-- Usage: psql "$DATABASE_URL" -f backend/scripts/list_broken_dose_response_curves.sql
SELECT * FROM (
  SELECT p.code, p.name AS protocol, p.status, r.name AS curve,
    CASE
      WHEN y.id IS NULL OR y.data_type <> 'numeric'
        THEN 'fits "' || coalesce(r.dose_response_config->>'y_readout_name', '')
             || '", which is not a numeric readout of this protocol'
      WHEN r.dose_response_config->>'x_readout_name' IS NOT NULL
           AND x.id IS NULL
           AND lower(trim(r.dose_response_config->>'x_readout_name'))
               NOT IN ('concentration', 'dose', 'well', 'plate', 'batch', 'compound')
        THEN 'uses "' || (r.dose_response_config->>'x_readout_name')
             || '" for concentration, which is not a readout of this protocol'
      WHEN r.dose_response_config->>'y_normalization' IS NOT NULL
           AND NOT (y.normalizations ? (r.dose_response_config->>'y_normalization'))
        THEN 'fits the ' || (r.dose_response_config->>'y_normalization')
             || ' layer, which "' || y.name || '" does not calculate'
      WHEN r.dose_response_config->>'y_normalization' IS NULL
           AND (SELECT count(*) FROM jsonb_array_elements_text(y.normalizations) n
                WHERE n <> 'none') >= 2
        THEN 'must say which layer of "' || y.name || '" it fits'
    END AS problem
  FROM readout_definitions r
  JOIN protocols p ON p.id = r.protocol_id
  LEFT JOIN readout_definitions y
    ON y.protocol_id = r.protocol_id AND y.name = r.dose_response_config->>'y_readout_name'
  LEFT JOIN readout_definitions x
    ON x.protocol_id = r.protocol_id AND x.name = r.dose_response_config->>'x_readout_name'
  WHERE r.data_type = 'dose_response'
) q
WHERE problem IS NOT NULL
ORDER BY code, curve;
