# LL-HLS Latency Monitoring
This tool is to measure the latancy of LL-HLS (Low-Latency HTTP Live Streaming) manifests and segments delivery via CDN, and display weak zones of low-latency live streams delivery.

## LL-HLS ±2.5 sec latency
With "correct" settings LL-HLS reaches ±2.5 seconds of glass-to-glass latency. Moreover, this is achieved even with transcoding in Cloud and distributing traffic via public CDN.
But not all tools/providers offer such settings by default. The tool is mainly to check that your CDN (and origin) really supports LL-HLS delivery, or what need to be adjusted.

# Why this tool
## What this tool can be used for
- Measuring delay in delivery of manifests (.m3u8/.m3u8?_HLS_msn=x&_HLS_part=y) and parts (.mp4/.m4v/etc).
- Measuring distribution of manifests and parts for different renditions.
- Summarize info about distribution latency.
- As a result, identifying weak points of distribution, so that you can understand the problem and correctly configure your CDN resource for low-latency distribution.

## What it is not suitable for
- This is not a LL-HLS manifest validator. For validation, use the media-stream-validator tool (https://developer.apple.com/documentation/http-live-streaming/using-apple-s-http-live-streaming-hls-tools).
- This is not a mp4-parts validator. For validation, use the same media-stream-validator tool.
- This is not a tool for CI (at least not yet).
- Does not work with regular HLS without parts (at least not yet).

## Example of why to use
LL-HLS protocol is very picky and sensitive to CDN settings. If LL-HLS output is delayed, then most likely your end-viewers will get the usual HLS delay (±9-30 seconds) instead of low-latency, or will see buffering. 
My analysis showed that implementation of the protocol varies greatly in different browsers and different players. For example, Safari browser is capricious about delays in manifest output from the very beginning of playback.


Safari browser (at least in versions 16-18.1) tries to download a high-quality rendition manifest, and measures its speed of distribution from the server. The first call is made without low-latency parameters, the second call with low-latency parameters. If it doesn't like the download speed, the browser will simply switch to a regular HLS without low latency.

What to do if the tool shows weak points:
- The tool downloads files locally. This means that connection from your local machine (where the test is running) to the server/CDN-edge may not be the best. Try other locations, for example, by taking several different virtual machines in different DCs. My experience shows that you can see a different picture in different places.
- If you see delays in manifests, then most likely packer on origin is slowly giving out manifests. Look at the performance of the origin server.
- If you see delays in parts, then most likely origin or CDN are slowly giving out files. Look at the performance of both, but first of all check parameters of CDN.

## LL-HLS protocol specification
The HLS specification defines low-latency extensions in HTTP Live Streaming 2nd Edition revision 7 and later. https://datatracker.ietf.org/doc/html/draft-pantos-hls-rfc8216bis 
Some explanation of enabling LL-HLS is here https://developer.apple.com/documentation/http-live-streaming/enabling-low-latency-http-live-streaming-hls 



# How to use
(TBD)
