# GADM 4.1 Vietnam level 1 — reproducible preparation

Run `python -m province_pipeline --config province_pipeline/config/example.json prepare-gadm`.
The source and derived GeoJSON/metadata are downloaded/generated in the checkout's gitignored config paths. GitHub runners regenerate them before exports, so users do not need to manually map province codes or create metadata.

- Source: https://geodata.ucdavis.edu/gadm/gadm4.1/json/gadm41_VNM_1.json.zip
- Version: GADM 4.1; named ZIP member timestamp 2022-07-18 (not a legal effective date).
- Conditions of use: https://gadm.org/license.html — check applicability to the intended research and distribution. Repository stores preparation code and identity crosswalk rather than redistributing source geometry.
- Archive SHA256: `1b82c4005ed5b4a0fead3c39c09720aa4664a394ed3b4c3e8056bca27a2fd989`.
- Original JSON SHA256: `fb7473e5f30c1de63d851c7505b3929527cdc6ceb82757ee765201a4b240ce9e`.
- Crosswalk: `gadm41_province_crosswalk.csv` maps all 63 exact GIDs and source names to the statistical code roster. GADM numeric identifiers are never treated as statistical codes. This is an identity mapping, not geometry/legal certification. The code roster reference is https://danhmuchanhchinh.gso.gov.vn/ and the repository's 63-province manifest.

The source downloaded for this change contained 63 valid Polygon/MultiPolygon features. Longitude extent was 102.145 to 109.4692 degrees. No geometries were invented, simplified, repaired, or extended. This extent must not be interpreted as a complete representation of all offshore/island territories or disputed areas. Check coastal/island research coverage against your chosen authoritative source.

GADM is used as a fixed research footprint with the pre-merger 63-province identity roster. It is **not labeled official 2024 geometry**. For that requirement, use the separate `official_2024` boundary policy and an independently sourced and verified dataset.

A projected topology audit (EPSG:6933) found 111 province pairs with overlap greater than 1 m². Sum of individual areas minus the union area is approximately 10.8894 km² (0.003307%). These source slivers are retained and recorded per pair in generated metadata `geometry_audit`; source validity does not imply zero overlap. Consider this before summing national province statistics. No complete national coverage/gap claim is made from this audit.
