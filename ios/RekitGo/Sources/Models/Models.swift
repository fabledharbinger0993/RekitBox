import Foundation

// MARK: - Server connection

struct ServerConfig: Codable {
    private static let minPort = 1
    private static let maxPort = 65535

    var host: String        // e.g. "100.94.x.x" (Tailscale) or LAN IP
    var port: Int = 5001
    var token: String

    private var normalizedHost: String? {
        let trimmedHost = host.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !trimmedHost.isEmpty else { return nil }

        if trimmedHost.hasPrefix("[") && trimmedHost.hasSuffix("]") {
            let start = trimmedHost.index(after: trimmedHost.startIndex)
            let end = trimmedHost.index(before: trimmedHost.endIndex)
            let unbracketedHost = String(trimmedHost[start..<end])
            return unbracketedHost.isEmpty ? nil : unbracketedHost
        }

        return trimmedHost
    }

    var baseURL: URL? {
        guard let normalizedHost, (Self.minPort...Self.maxPort).contains(port) else { return nil }

        var components = URLComponents()
        components.scheme = "http"
        components.host = normalizedHost
        components.port = port
        return components.url
    }
}

// MARK: - Track

struct Track: Identifiable, Codable, Hashable {
    let id: Int
    let title: String?
    let artist: String?
    let album: String?
    let bpm: Double?
    let key: String?
    let duration: Double?
    let filePath: String?
    let dateAdded: String?

    enum CodingKeys: String, CodingKey {
        case id, title, artist, album, bpm, key, duration
        case filePath  = "file_path"
        case dateAdded = "date_added"
    }

    var displayTitle:  String { title  ?? "Unknown Title" }
    var displayArtist: String { artist ?? "Unknown Artist" }
}

// MARK: - Playlist

struct Playlist: Identifiable, Codable, Hashable {
    let id: Int
    let name: String
    let trackCount: Int?
    var tracks: [Track]?

    enum CodingKeys: String, CodingKey {
        case id, name, tracks
        case trackCount = "track_count"
    }
}

// MARK: - Download job

struct DownloadJob: Identifiable, Codable {
    let jobId: String
    let url: String
    let destination: String
    let format: String
    var status: DownloadStatus
    var progress: Int
    var title: String?
    var artist: String?
    var filePath: String?
    var error: String?

    var id: String { jobId }

    enum CodingKeys: String, CodingKey {
        case jobId = "job_id"
        case url, destination, format, status, progress, title, artist, error
        case filePath = "file_path"
    }
}

enum DownloadStatus: String, Codable {
    case queued, downloading, converting, importing, done, failed
}

// MARK: - Analysis job

struct AnalysisJob: Codable {
    let jobId: String
    var status: String
    var results: [String: AnalysisResult]

    enum CodingKeys: String, CodingKey {
        case jobId = "job_id"
        case status, results
    }
}

struct AnalysisResult: Codable {
    var status: String
    var bpm: Double?
    var key: String?
    var error: String?
}

// MARK: - Drive

struct Drive: Identifiable, Codable {
    let name: String
    let path: String
    let pioneer: Bool
    var id: String { path }
}

struct Folder: Identifiable, Codable, Hashable {
    let name: String
    let path: String
    let fileCount: Int?

    var id: String { path }

    enum CodingKeys: String, CodingKey {
        case name, path
        case fileCount = "file_count"
    }
}

// MARK: - Export job

struct ExportJob: Codable {
    let jobId: String
    var status: String
    var progress: Int
    var message: String?

    enum CodingKeys: String, CodingKey {
        case jobId = "job_id"
        case status, progress, message
    }
}
