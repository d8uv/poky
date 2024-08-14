#
# Copyright OpenEmbedded Contributors
#
# SPDX-License-Identifier: MIT
#

import collections
import re
import itertools
import functools

_Version = collections.namedtuple(
    "_Version", ["release", "patch_l", "pre_l", "pre_v"]
)

@functools.total_ordering
class Version():

    def __init__(self, version, suffix=None):

        suffixes = ["alphabetical", "patch"]

        if str(suffix) == "alphabetical":
            version_pattern =  r"""r?v?(?:(?P<release>[0-9]+(?:[-\.][0-9]+)*)(?P<patch>[-_\.]?(?P<patch_l>[a-z]))?(?P<pre>[-_\.]?(?P<pre_l>(rc|alpha|beta|pre|preview|dev))[-_\.]?(?P<pre_v>[0-9]+)?)?)(.*)?"""
        elif str(suffix) == "patch":
            version_pattern =  r"""r?v?(?:(?P<release>[0-9]+(?:[-\.][0-9]+)*)(?P<patch>[-_\.]?(p|patch)(?P<patch_l>[0-9]+))?(?P<pre>[-_\.]?(?P<pre_l>(rc|alpha|beta|pre|preview|dev))[-_\.]?(?P<pre_v>[0-9]+)?)?)(.*)?"""
        else:
            version_pattern =  r"""r?v?(?:(?P<release>[0-9]+(?:[-\.][0-9]+)*)(?P<pre>[-_\.]?(?P<pre_l>(rc|alpha|beta|pre|preview|dev))[-_\.]?(?P<pre_v>[0-9]+)?)?)(.*)?"""
        regex = re.compile(r"^\s*" + version_pattern + r"\s*$", re.VERBOSE | re.IGNORECASE)

        match = regex.search(version)
        if not match:
            raise Exception("Invalid version: '{0}'".format(version))

        self._version = _Version(
            release=tuple(int(i) for i in match.group("release").replace("-",".").split(".")),
            patch_l=match.group("patch_l") if str(suffix) in suffixes and match.group("patch_l") else "",
            pre_l=match.group("pre_l"),
            pre_v=match.group("pre_v")
        )

        self._key = _cmpkey(
            self._version.release,
            self._version.patch_l,
            self._version.pre_l,
            self._version.pre_v
        )

    def __eq__(self, other):
        if not isinstance(other, Version):
            return NotImplemented
        return self._key == other._key

    def __gt__(self, other):
        if not isinstance(other, Version):
            return NotImplemented
        return self._key > other._key

def _cmpkey(release, patch_l, pre_l, pre_v):
    # remove leading 0
    _release = tuple(
        reversed(list(itertools.dropwhile(lambda x: x == 0, reversed(release))))
    )

    _patch = patch_l.upper()

    if pre_l is None and pre_v is None:
        _pre = float('inf')
    else:
        _pre = float(pre_v) if pre_v else float('-inf')
    return _release, _patch, _pre


def get_patched_cves(d):
    """
    Get patches that solve CVEs using the "CVE: " tag.
    """

    import re
    import oe.patch

    cve_match = re.compile(r"CVE:( CVE-\d{4}-\d+)+")

    # Matches the last "CVE-YYYY-ID" in the file name, also if written
    # in lowercase. Possible to have multiple CVE IDs in a single
    # file name, but only the last one will be detected from the file name.
    # However, patch files contents addressing multiple CVE IDs are supported
    # (cve_match regular expression)
    cve_file_name_match = re.compile(r".*(CVE-\d{4}-\d+)", re.IGNORECASE)

    patched_cves = {}
    patches = oe.patch.src_patches(d)
    bb.debug(2, "Scanning %d patches for CVEs" % len(patches))
    for url in patches:
        patch_file = bb.fetch.decodeurl(url)[2]

        # Check patch file name for CVE ID
        fname_match = cve_file_name_match.search(patch_file)
        if fname_match:
            cve = fname_match.group(1).upper()
            patched_cves[cve] = {"abbrev-status": "Patched", "status": "fix-file-included", "resource": patch_file}
            bb.debug(2, "Found %s from patch file name %s" % (cve, patch_file))

        # Remote patches won't be present and compressed patches won't be
        # unpacked, so say we're not scanning them
        if not os.path.isfile(patch_file):
            bb.note("%s is remote or compressed, not scanning content" % patch_file)
            continue

        with open(patch_file, "r", encoding="utf-8") as f:
            try:
                patch_text = f.read()
            except UnicodeDecodeError:
                bb.debug(1, "Failed to read patch %s using UTF-8 encoding"
                        " trying with iso8859-1" %  patch_file)
                f.close()
                with open(patch_file, "r", encoding="iso8859-1") as f:
                    patch_text = f.read()

        # Search for one or more "CVE: " lines
        text_match = False
        for match in cve_match.finditer(patch_text):
            # Get only the CVEs without the "CVE: " tag
            cves = patch_text[match.start()+5:match.end()]
            for cve in cves.split():
                bb.debug(2, "Patch %s solves %s" % (patch_file, cve))
                patched_cves[cve] = {"abbrev-status": "Patched", "status": "fix-file-included", "resource": patch_file}
                text_match = True

        if not fname_match and not text_match:
            bb.debug(2, "Patch %s doesn't solve CVEs" % patch_file)

    # Search for additional patched CVEs
    for cve in (d.getVarFlags("CVE_STATUS") or {}):
        decoded_status = decode_cve_status(d, cve)
        products = d.getVar("CVE_PRODUCT")
        if has_cve_product_match(decoded_status, products) == True:
            patched_cves[cve] = {
                "abbrev-status": decoded_status["mapping"],
                "status": decoded_status["detail"],
                "justification": decoded_status["description"],
                "affected-vendor": decoded_status["vendor"],
                "affected-product": decoded_status["product"]
            }

    return patched_cves


def get_cpe_ids(cve_product, version):
    """
    Get list of CPE identifiers for the given product and version
    """

    version = version.split("+git")[0]

    cpe_ids = []
    for product in cve_product.split():
        # CVE_PRODUCT in recipes may include vendor information for CPE identifiers. If not,
        # use wildcard for vendor.
        if ":" in product:
            vendor, product = product.split(":", 1)
        else:
            vendor = "*"

        cpe_id = 'cpe:2.3:*:{}:{}:{}:*:*:*:*:*:*:*'.format(vendor, product, version)
        cpe_ids.append(cpe_id)

    return cpe_ids

def cve_check_merge_jsons(output, data):
    """
    Merge the data in the "package" property to the main data file
    output
    """
    if output["version"] != data["version"]:
        bb.error("Version mismatch when merging JSON outputs")
        return

    for product in output["package"]:
        if product["name"] == data["package"][0]["name"]:
            bb.error("Error adding the same package %s twice" % product["name"])
            return

    output["package"].append(data["package"][0])

def update_symlinks(target_path, link_path):
    """
    Update a symbolic link link_path to point to target_path.
    Remove the link and recreate it if exist and is different.
    """
    if link_path != target_path and os.path.exists(target_path):
        if os.path.exists(os.path.realpath(link_path)):
            os.remove(link_path)
        os.symlink(os.path.basename(target_path), link_path)


def convert_cve_version(version):
    """
    This function converts from CVE format to Yocto version format.
    eg 8.3_p1 -> 8.3p1, 6.2_rc1 -> 6.2-rc1

    Unless it is redefined using CVE_VERSION in the recipe,
    cve_check uses the version in the name of the recipe (${PV})
    to check vulnerabilities against a CVE in the database downloaded from NVD.

    When the version has an update, i.e.
    "p1" in OpenSSH 8.3p1,
    "-rc1" in linux kernel 6.2-rc1,
    the database stores the version as version_update (8.3_p1, 6.2_rc1).
    Therefore, we must transform this version before comparing to the
    recipe version.

    In this case, the parameter of the function is 8.3_p1.
    If the version uses the Release Candidate format, "rc",
    this function replaces the '_' by '-'.
    If the version uses the Update format, "p",
    this function removes the '_' completely.
    """
    import re

    matches = re.match('^([0-9.]+)_((p|rc)[0-9]+)$', version)

    if not matches:
        return version

    version = matches.group(1)
    update = matches.group(2)

    if matches.group(3) == "rc":
        return version + '-' + update

    return version + update

def decode_cve_status(d, cve):
    """
    Convert CVE_STATUS into status, vendor, product, detail and description.
    """
    status = d.getVarFlag("CVE_STATUS", cve)
    if not status:
        return {}

    status_split = status.split(':', 5)
    status_out = {}
    status_out["detail"] = status_split[0]
    product = "*"
    vendor = "*"
    description = ""
    if len(status_split) >= 4 and status_split[1].strip() == "cpe":
        # Both vendor and product are mandatory if cpe: present, the syntax is then:
        # detail: cpe:vendor:product:description
        vendor = status_split[2].strip()
        product = status_split[3].strip()
        description = status_split[4].strip()
    elif len(status_split) >= 2 and status_split[1].strip() == "cpe":
        # Malformed CPE
        bb.warn('Invalid CPE information for CVE_STATUS[%s] = "%s", not setting CPE' % (detail, cve, status))
    else:
        # Other case: no CPE, the syntax is then:
        # detail: description
        description = status_split[len(status_split)-1].strip() if (len(status_split) > 1) else ""

    status_out["vendor"] = vendor
    status_out["product"] = product
    status_out["description"] = description

    status_mapping = d.getVarFlag("CVE_CHECK_STATUSMAP", status_out['detail'])
    if status_mapping is None:
        bb.warn('Invalid detail "%s" for CVE_STATUS[%s] = "%s", fallback to Unpatched' % (detail, cve, status))
        status_mapping = "Unpatched"
    status_out["mapping"] = status_mapping

    return status_out

def has_cve_product_match(detailed_status, products):
    """
    Check product/vendor match between detailed_status from decode_cve_status and a string of
    products (like from CVE_PRODUCT)
    """
    for product in products.split():
        vendor = "*"
        if ":" in product:
            vendor, product = product.split(":", 1)

        if (vendor == detailed_status["vendor"] or detailed_status["vendor"] == "*") and \
            (product == detailed_status["product"] or detailed_status["product"] == "*"):
            return True

    #if no match, return False
    return False
