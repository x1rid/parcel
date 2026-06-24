FORMATS = ["MP4", "MKV", "MOV", "AVI", "WEBM"]

FORMAT_CODEC_SUPPORT = {
    "MP4": ["H264", "H265", "AV1"],
    "MKV": ["H264", "H265", "AV1", "VP9"],
    "MOV": ["H264", "H265"],
    "AVI": ["H264"],
    "WEBM": ["VP9", "AV1"]
}

ENCODERS = ["NVIDIA NVENC", "Intel QuickSync", "AMD AMF", "x264", "x265", "AV1"]

# Maps UI selection to the actual FFmpeg codec string
CODEC_MAP = {
    "H264": {
        "NVIDIA NVENC": "h264_nvenc",
        "Intel QuickSync": "h264_qsv",
        "AMD AMF": "h264_amf",
        "x264": "libx264"
    },
    "H265": {
        "NVIDIA NVENC": "hevc_nvenc",
        "Intel QuickSync": "hevc_qsv",
        "AMD AMF": "hevc_amf",
        "x265": "libx265"
    },
    "AV1": {
        "NVIDIA NVENC": "av1_nvenc",
        "Intel QuickSync": "av1_qsv",
        "AMD AMF": "av1_amf",
        "AV1": "libaom-av1"
    },
    "VP9": {
        "x264": "libvpx-vp9", # Fallback software
        "x265": "libvpx-vp9"
    }
}

RESOLUTIONS = ["Original", "2160p", "1440p", "1080p", "720p", "480p", "Custom"]
FPS_OPTIONS = ["Original", "60", "30", "24", "Custom"]
QUALITIES = ["Fastest", "Fast", "Balanced", "Quality", "Best Quality"]
AUDIO_BITRATES = ["64", "96", "128", "192", "256", "320"]

def get_resolution_scale(res_string):
    scales = {
        "2160p": "scale=-2:2160",
        "1440p": "scale=-2:1440",
        "1080p": "scale=-2:1080",
        "720p": "scale=-2:720",
        "480p": "scale=-2:480"
    }
    return scales.get(res_string, None)