import zipfile
from dataclasses import dataclass, field
from pathlib import Path
from lxml import etree


@dataclass
class ParsedPaper:
    doi: str
    version: int
    title: str
    subject: str | None
    authors: list[dict]
    posted_date: str | None
    abstract: str
    sections: list[tuple[str, str]] = field(default_factory=list)


def extract_meca(meca_path: Path, dest_dir: Path) -> tuple[Path | None, Path | None]:
    """Unzip a MECA. Returns (jats_xml_path, manifest_path)."""
    dest_dir.mkdir(parents=True, exist_ok=True)
    jats: Path | None = None
    manifest: Path | None = None
    with zipfile.ZipFile(meca_path, "r") as zf:
        for name in zf.namelist():
            lower = name.lower()
            if lower.endswith("manifest.xml"):
                target = dest_dir / "manifest.xml"
                target.write_bytes(zf.read(name))
                manifest = target
            elif lower.startswith("content/") and lower.endswith(".xml"):
                target = dest_dir / Path(name).name
                target.write_bytes(zf.read(name))
                if jats is None or "manifest" not in target.name.lower():
                    jats = target
    return jats, manifest


def _txt(node) -> str:
    if node is None:
        return ""
    return " ".join(node.itertext()).strip()


_SUBJECT_PRIORITY = ("bioRxiv", "medRxiv", "hwp-journal-coll", "categories", "subject")


def _extract_subject(root) -> str | None:
    """Pick the most specific bioRxiv/medRxiv category, skipping the
    generic 'heading' (e.g. "Regular Article") group."""
    groups = root.findall(".//subj-group")
    by_type: dict[str, str] = {}
    untyped: str | None = None
    for sg in groups:
        sg_type = sg.get("subj-group-type") or ""
        subj = _txt(sg.find("subject"))
        if not subj or sg_type == "heading":
            continue
        if sg_type:
            by_type.setdefault(sg_type, subj)
        elif untyped is None:
            untyped = subj
    for pref in _SUBJECT_PRIORITY:
        if pref in by_type:
            return by_type[pref]
    if by_type:
        return next(iter(by_type.values()))
    return untyped


def parse_jats(jats_path: Path) -> ParsedPaper:
    parser = etree.XMLParser(recover=True, huge_tree=True, load_dtd=False, no_network=True)
    tree = etree.parse(str(jats_path), parser=parser)
    root = tree.getroot()

    doi = _txt(root.find('.//article-id[@pub-id-type="doi"]'))
    title = _txt(root.find(".//title-group/article-title")) or _txt(root.find(".//article-title"))
    subject = _extract_subject(root)

    authors: list[dict] = []
    for c in root.findall('.//contrib[@contrib-type="author"]'):
        surname = _txt(c.find(".//surname"))
        given = _txt(c.find(".//given-names"))
        affs = [_txt(a) for a in c.findall(".//aff") if _txt(a)]
        if surname or given:
            authors.append({"surname": surname, "given": given, "affiliations": affs})

    pub_date = root.find('.//pub-date[@date-type="pub"]')
    if pub_date is None:
        pub_date = root.find('.//pub-date[@pub-type="epub"]')
    if pub_date is None:
        pub_date = root.find(".//pub-date")
    posted_date: str | None = None
    if pub_date is not None:
        y = _txt(pub_date.find("year"))
        m = _txt(pub_date.find("month")) or "01"
        d = _txt(pub_date.find("day")) or "01"
        if y.isdigit():
            try:
                posted_date = f"{int(y):04d}-{int(m):02d}-{int(d):02d}"
            except ValueError:
                posted_date = None

    version = 1
    ver_el = root.find(".//article-version")
    if ver_el is not None:
        v = _txt(ver_el)
        if v.isdigit():
            version = int(v)

    abstract = _txt(root.find(".//abstract"))

    sections: list[tuple[str, str]] = []
    body = root.find(".//body")
    if body is not None:
        for sec in body.findall(".//sec"):
            label = sec.get("sec-type") or _txt(sec.find("title")) or "section"
            text = _txt(sec)
            if text and len(text) > 50:
                sections.append((label.lower(), text))

    return ParsedPaper(
        doi=doi,
        version=version,
        title=title,
        subject=subject,
        authors=authors,
        posted_date=posted_date,
        abstract=abstract,
        sections=sections,
    )
