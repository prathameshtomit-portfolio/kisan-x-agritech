from fastapi import APIRouter

from app.services.catalog_service import load_catalogue

router = APIRouter(prefix="/catalog", tags=["evidence catalogue"])


@router.get("")
def get_catalogue():
    """Expose reviewed crop and rule availability to web and native clients."""
    catalogue = load_catalogue()
    return {
        "version": catalogue.version,
        "crop_count": len(catalogue.crop_catalogue.crops),
        "rule_count": len(catalogue.rule_catalogue.rules),
        "crops": [crop.model_dump() for crop in catalogue.crop_catalogue.crops],
        "sources": [source.model_dump() for source in catalogue.crop_catalogue.sources],
        "limitations": [
            "Only reviewed catalogue entries are shown as supported crop evidence.",
            "An empty catalogue means the service cannot establish crop eligibility.",
        ],
    }
