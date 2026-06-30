# Shared config: which fields per data file hold translatable prose.
# Company names / place names / codes are intentionally excluded.
PROSE_FIELDS = {
    'core_materials.json': ['type', 'note', 'verdict', 'gs', 'tagline', 'need',
        'why_qcc_misses', 'strategic', 'backup', 'risk', 'import_origin',
        'tag_cn', 'basis', 'title', 'headline', 'disclaimer', 'caption'],
    'services.json': ['type', 'note', 'tagline', 'model', 'redline', 'feature', 'title', 'sub'],
    'equipment.json': ['note', 'special_notes', 'reference_price_desc', 'spec',
        'edge', 'source', 'feature', 'qualification', 'title', 'sub'],
    'service_rates.json': ['name', 'note', 'short', 'desc', 'url'],
    'web_reputation.json': ['tag', 'note'],
}
