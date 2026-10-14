-- SQL CHECK treats NULL as passing; require the keys and typed false flags explicitly.
ALTER TABLE marketpulse.projections ADD CONSTRAINT projection_required_keys CHECK (
    payload ?& ARRAY['schema','kind','availability_tier','paper_action_authorized',
                    'deployment_promoted','rows','classes','probabilities','live']
    AND payload->'paper_action_authorized' = 'false'::jsonb
    AND payload->'deployment_promoted' = 'false'::jsonb
    AND payload->>'kind' = kind
    AND payload->'classes' = '["DOWN","NO_MATERIAL_MOVE","UP"]'::jsonb
    AND jsonb_typeof(payload->'rows') = 'array'
    AND jsonb_typeof(payload->'probabilities') = 'object'
    AND ((kind='research' AND payload->'live'='false'::jsonb)
        OR (kind='forward' AND payload->'live'='true'::jsonb))
);
