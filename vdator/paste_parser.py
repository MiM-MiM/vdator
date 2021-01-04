from dotenv import load_dotenv
from enum import Enum
import os, re

# load environment variables
load_dotenv()

# environment variables
IGNORE_AFTER_LINE = os.environ.get("IGNORE_AFTER_LINE").strip()
IGNORE_AFTER_LINE_METHOD = os.environ.get("IGNORE_AFTER_LINE_METHOD").strip()
IGNORE_UNTIL_BLANK_LINE_PREFIXES = [
    x.strip()
    for x in os.getenv("IGNORE_UNTIL_BLANK_LINE_PREFIXES", "").strip().split(",")
]


class BDInfoType(Enum):
    QUICK_SUMMARY = 1
    PLAYLIST_REPORT = 2


class PasteParser:
    def __init__(self, bdinfo_parser):
        self.bdinfo_parser = bdinfo_parser

    class Section(Enum):
        QUICK_SUMMARY = 1
        MEDIAINFO = 2
        PLAYLIST_REPORT = 3
        EAC3TO_LOG = 4

    class Section2(Enum):
        PLAYLIST_VIDEO = 1
        PLAYLIST_AUDIO = 2
        PLAYLIST_SUBTITLES = 3

    class Section3(Enum):
        PLAYLIST_INNER_VIDEO = 1
        PLAYLIST_INNER_AUDIO = 2

    def parse(self, text):
        """
        Parse text to extract bdinfo, mediainfo and eac3to log

        Parameters
        ----------
        text : str
            text to parse

        Returns
        -------
        bdinfo, mediainfo, and eac3to lists
        """
        bdinfo = {"video": list(), "audio": list(), "subtitle": list()}
        mediainfo = list()
        eac3to = list()
        eac3to_index = -1

        sect = None
        sect2 = None
        sect3 = None

        # parse bdinfo
        lines = text.splitlines()
        ignore_next_lines, did_first_mediainfo = False, False
        for l in lines:
            # break after ignore line
            if self._isIgnoreAfterLine(l):
                break

            if not l.strip():
                # don't ignore input after blank line
                ignore_next_lines = False
                # skip blank lines
                continue

            if ignore_next_lines:
                continue

            if (
                IGNORE_UNTIL_BLANK_LINE_PREFIXES
                and IGNORE_UNTIL_BLANK_LINE_PREFIXES[0] != ""
            ):
                l3 = l.strip().lower()
                for x in IGNORE_UNTIL_BLANK_LINE_PREFIXES:
                    if l3.startswith(x):
                        ignore_next_lines = True
                        break

            l2 = l.strip().lower()

            # determine current section
            # limit to first mediainfo
            if l2.startswith("quick summary"):
                sect = self.Section.QUICK_SUMMARY
                bdinfo["type"] = BDInfoType.QUICK_SUMMARY
            elif l2.startswith("playlist report"):
                sect = self.Section.PLAYLIST_REPORT
                bdinfo["type"] = BDInfoType.PLAYLIST_REPORT
            elif l2.startswith("eac3to v"):
                sect = self.Section.EAC3TO_LOG
                eac3to.append(list())
                eac3to_index += 1
            elif l2.startswith("general"):
                if did_first_mediainfo:
                    sect = None
                else:
                    sect = self.Section.MEDIAINFO
                    did_first_mediainfo = True

            if sect == self.Section.QUICK_SUMMARY:
                if l2.startswith("video:"):
                    track_name = l.split(":", 1)[1]
                    track_name = self.bdinfo_parser.format_video_track_name(track_name)
                    bdinfo["video"].append(track_name)
                elif l2.startswith("audio:"):
                    audio_name = l.split(":", 1)[1].strip()
                    if "ac3 embedded" in audio_name.lower():
                        audio_parts = re.split(
                            r"\(ac3 embedded:", audio_name, flags=re.IGNORECASE
                        )
                        bdinfo["audio"].append(
                            self.bdinfo_parser.format_track_name(audio_parts[0])
                        )
                        compat_track = (
                            "Compatibility Track / Dolby Digital Audio / "
                            + audio_parts[1].strip().rstrip(")")
                        )
                        bdinfo["audio"].append(
                            self.bdinfo_parser.format_track_name(compat_track)
                        )
                    else:
                        if "(" in l:
                            l = l.split("(")[0]
                        l = l.strip()
                        bdinfo["audio"].append(
                            self.bdinfo_parser.format_track_name(l.split(":", 1)[1])
                        )
                elif l2.startswith("subtitle:"):
                    bdinfo["subtitle"].append(
                        self.bdinfo_parser.format_track_name(l.split(":", 1)[1])
                    )

            elif sect == self.Section.PLAYLIST_REPORT:

                if l2.startswith("video:"):
                    sect2 = self.Section2.PLAYLIST_VIDEO
                elif l2.startswith("audio:"):
                    sect2 = self.Section2.PLAYLIST_AUDIO
                elif l2.startswith("subtitles:"):
                    sect2 = self.Section2.PLAYLIST_SUBTITLES

                if l2.startswith("-----"):
                    if sect2 == self.Section2.PLAYLIST_VIDEO:
                        sect3 = self.Section3.PLAYLIST_INNER_VIDEO
                    elif sect2 == self.Section2.PLAYLIST_AUDIO:
                        sect3 = self.Section3.PLAYLIST_INNER_AUDIO
                else:
                    # skip tracks that start with minus sign
                    if l.startswith("-"):
                        continue

                    if (
                        sect2 == self.Section2.PLAYLIST_VIDEO
                        and sect3 == self.Section3.PLAYLIST_INNER_VIDEO
                    ):
                        # format video track name with slashes
                        track_name = (
                            self.bdinfo_parser.playlist_report_format_video_track_name(
                                l
                            )
                        )
                        if track_name:
                            bdinfo["video"].append(track_name)

                    elif (
                        sect2 == self.Section2.PLAYLIST_AUDIO
                        and sect3 == self.Section3.PLAYLIST_INNER_AUDIO
                    ):
                        track_name = (
                            self.bdinfo_parser.playlist_report_format_audio_track_name(
                                l
                            )
                        )
                        if track_name:
                            bdinfo["audio"].append(track_name)

                        if "ac3 embedded" in l.lower():
                            audio_parts = re.split(
                                r"\(ac3 embedded:", l, flags=re.IGNORECASE
                            )
                            compat_track = (
                                "Compatibility Track / Dolby Digital Audio / "
                                + "/".join(audio_parts[1].split("/")[:-1])
                                .strip()
                                .rstrip(")")
                            )
                            bdinfo["audio"].append(
                                self.bdinfo_parser.format_track_name(compat_track)
                            )

            elif sect == self.Section.MEDIAINFO:
                mediainfo.append(l)

            elif sect == self.Section.EAC3TO_LOG:
                if l.startswith("Done."):
                    sect = None
                else:
                    eac3to[eac3to_index].append(l)

        return bdinfo, mediainfo, eac3to

    def _isIgnoreAfterLine(self, l):
        """
        Check if we should ignore all input after the current line

        Parameters
        ----------
        l : str
            current line

        Returns
        -------
        True if should ignore further input, False otherwise
        """
        if IGNORE_AFTER_LINE_METHOD == "equals":
            if IGNORE_AFTER_LINE == l:
                return True
        elif IGNORE_AFTER_LINE_METHOD == "contains":
            if IGNORE_AFTER_LINE in l:
                return True
        return False
