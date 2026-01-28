import { useEffect, useState } from 'react'
import { listFiles, deleteFile, getFileUrl, getThumbnailUrl, getYouTubeStatus, listYouTubeAccounts, uploadToYouTube } from '../api/client'
import type { FileInfo } from '../api/types'

function formatSize(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`
  if (bytes < 1024 * 1024 * 1024) return `${(bytes / (1024 * 1024)).toFixed(1)} MB`
  return `${(bytes / (1024 * 1024 * 1024)).toFixed(2)} GB`
}

function formatDate(dateString: string): string {
  return new Date(dateString).toLocaleString()
}

type YouTubeStatus = {
  configured: boolean
  authenticated: boolean
  setup_needed: boolean
  auth_needed: boolean
}

export default function Files() {
  const [files, setFiles] = useState<FileInfo[]>([])
  const [loading, setLoading] = useState(true)
  const [view, setView] = useState<'grid' | 'list'>('grid')
  const [videosOnly, setVideosOnly] = useState(true)
  const [previewFile, setPreviewFile] = useState<FileInfo | null>(null)
  const [youtubeStatus, setYoutubeStatus] = useState<YouTubeStatus | null>(null)
  const [youtubeAccounts, setYoutubeAccounts] = useState<Array<{ name: string; file: string }>>([])
  const [uploadFile, setUploadFile] = useState<FileInfo | null>(null)
  const [uploadTitle, setUploadTitle] = useState('')
  const [uploadDescription, setUploadDescription] = useState('')
  const [uploadPrivacy, setUploadPrivacy] = useState('unlisted')
  const [uploadAccount, setUploadAccount] = useState('')
  const [uploading, setUploading] = useState(false)
  const [uploadResult, setUploadResult] = useState<{ url?: string; error?: string } | null>(null)

  useEffect(() => {
    async function fetchFiles() {
      try {
        const data = await listFiles({ videos_only: videosOnly })
        setFiles(data)
      } catch (error) {
        console.error('Failed to fetch files:', error)
      } finally {
        setLoading(false)
      }
    }

    fetchFiles()
  }, [videosOnly])

  useEffect(() => {
    Promise.all([getYouTubeStatus(), listYouTubeAccounts()])
      .then(([status, accounts]) => {
        setYoutubeStatus(status)
        setYoutubeAccounts(accounts.accounts)
        setUploadAccount(accounts.default)
      })
      .catch(() => {})
  }, [])

  const handleDelete = async (filename: string) => {
    if (!confirm(`Delete ${filename} and related files?`)) return
    try {
      await deleteFile(filename)
      setFiles((prev) => prev.filter((f) => f.name !== filename))
      if (previewFile?.name === filename) {
        setPreviewFile(null)
      }
    } catch (error) {
      console.error('Failed to delete file:', error)
    }
  }

  const handleUploadToYouTube = (file: FileInfo) => {
    setUploadFile(file)
    setUploadTitle(file.name.replace(/\.[^.]+$/, '').replace(/[-_]/g, ' '))
    setUploadDescription('')
    setUploadPrivacy('unlisted')
    setUploadResult(null)
  }

  const handleUploadSubmit = async () => {
    if (!uploadFile || !uploadTitle) return

    setUploading(true)
    setUploadResult(null)

    try {
      const result = await uploadToYouTube({
        filename: uploadFile.name,
        title: uploadTitle,
        description: uploadDescription,
        privacy: uploadPrivacy,
        account: uploadAccount,
      })

      if (result.status === 'success') {
        setUploadResult({ url: result.url })
      } else {
        setUploadResult({ error: result.error || result.message })
      }
    } catch (error) {
      setUploadResult({ error: error instanceof Error ? error.message : 'Upload failed' })
    } finally {
      setUploading(false)
    }
  }

  const totalSize = files.reduce((sum, f) => sum + f.size, 0)

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-gray-900">Files</h1>
          <p className="mt-1 text-gray-600">
            {files.length} files ({formatSize(totalSize)})
          </p>
        </div>
        <div className="flex items-center gap-4">
          <label className="flex items-center text-sm text-gray-600">
            <input
              type="checkbox"
              checked={videosOnly}
              onChange={(e) => setVideosOnly(e.target.checked)}
              className="rounded border-gray-300 text-frigate-600 focus:ring-frigate-500 mr-2"
            />
            Videos only
          </label>
          <div className="flex rounded-lg border border-gray-200 overflow-hidden">
            <button
              onClick={() => setView('grid')}
              className={`px-3 py-1.5 text-sm ${
                view === 'grid'
                  ? 'bg-frigate-600 text-white'
                  : 'bg-white text-gray-600 hover:bg-gray-50'
              }`}
            >
              <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 6a2 2 0 012-2h2a2 2 0 012 2v2a2 2 0 01-2 2H6a2 2 0 01-2-2V6zM14 6a2 2 0 012-2h2a2 2 0 012 2v2a2 2 0 01-2 2h-2a2 2 0 01-2-2V6zM4 16a2 2 0 012-2h2a2 2 0 012 2v2a2 2 0 01-2 2H6a2 2 0 01-2-2v-2zM14 16a2 2 0 012-2h2a2 2 0 012 2v2a2 2 0 01-2 2h-2a2 2 0 01-2-2v-2z" />
              </svg>
            </button>
            <button
              onClick={() => setView('list')}
              className={`px-3 py-1.5 text-sm ${
                view === 'list'
                  ? 'bg-frigate-600 text-white'
                  : 'bg-white text-gray-600 hover:bg-gray-50'
              }`}
            >
              <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 6h16M4 10h16M4 14h16M4 18h16" />
              </svg>
            </button>
          </div>
        </div>
      </div>

      {loading ? (
        <div className="flex items-center justify-center h-64">
          <div className="text-gray-500">Loading...</div>
        </div>
      ) : files.length === 0 ? (
        <div className="bg-white rounded-xl shadow-sm border border-gray-200 p-12 text-center">
          <svg className="w-16 h-16 mx-auto text-gray-400 mb-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 19a2 2 0 01-2-2V7a2 2 0 012-2h4l2 2h4a2 2 0 012 2v1M5 19h14a2 2 0 002-2v-5a2 2 0 00-2-2H9a2 2 0 00-2 2v5a2 2 0 01-2 2z" />
          </svg>
          <p className="text-gray-500">No files found</p>
        </div>
      ) : view === 'grid' ? (
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-4">
          {files.map((file) => (
            <div
              key={file.name}
              className="bg-white rounded-xl shadow-sm border border-gray-200 overflow-hidden hover:shadow-md transition-shadow"
            >
              <div
                className="aspect-video bg-gray-100 flex items-center justify-center cursor-pointer relative group"
                onClick={() => setPreviewFile(file)}
              >
                {file.is_video ? (
                  <>
                    <img
                      src={getThumbnailUrl(file.name)}
                      alt={file.name}
                      className="w-full h-full object-cover"
                      onError={(e) => {
                        // Hide broken image and show fallback
                        e.currentTarget.style.display = 'none'
                        e.currentTarget.nextElementSibling?.classList.remove('hidden')
                      }}
                    />
                    <div className="hidden absolute inset-0 flex items-center justify-center bg-gray-100">
                      <svg className="w-12 h-12 text-gray-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M14.752 11.168l-3.197-2.132A1 1 0 0010 9.87v4.263a1 1 0 001.555.832l3.197-2.132a1 1 0 000-1.664z" />
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
                      </svg>
                    </div>
                    <div className="absolute inset-0 bg-black/30 opacity-0 group-hover:opacity-100 transition-opacity flex items-center justify-center">
                      <svg className="w-12 h-12 text-white" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M14.752 11.168l-3.197-2.132A1 1 0 0010 9.87v4.263a1 1 0 001.555.832l3.197-2.132a1 1 0 000-1.664z" />
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
                      </svg>
                    </div>
                  </>
                ) : (
                  <svg className="w-12 h-12 text-gray-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
                  </svg>
                )}
              </div>
              <div className="p-4">
                <h3 className="font-medium text-gray-900 truncate" title={file.name}>
                  {file.name}
                </h3>
                <p className="text-sm text-gray-500 mt-1">
                  {formatSize(file.size)} • {formatDate(file.modified)}
                </p>
                <div className="flex gap-2 mt-3">
                  <a
                    href={getFileUrl(file.name)}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="flex-1 text-center px-3 py-1.5 text-sm font-medium text-frigate-600 bg-frigate-50 rounded-lg hover:bg-frigate-100"
                  >
                    View
                  </a>
                  <a
                    href={getFileUrl(file.name, true)}
                    className="flex-1 text-center px-3 py-1.5 text-sm font-medium text-gray-600 bg-gray-100 rounded-lg hover:bg-gray-200"
                  >
                    Download
                  </a>
                  {youtubeStatus?.configured && file.is_video && (
                    <button
                      onClick={() => handleUploadToYouTube(file)}
                      className="px-3 py-1.5 text-sm font-medium text-red-600 bg-red-50 rounded-lg hover:bg-red-100"
                      title="Upload to YouTube"
                    >
                      <svg className="w-4 h-4" viewBox="0 0 24 24" fill="currentColor">
                        <path d="M23.498 6.186a3.016 3.016 0 0 0-2.122-2.136C19.505 3.545 12 3.545 12 3.545s-7.505 0-9.377.505A3.017 3.017 0 0 0 .502 6.186C0 8.07 0 12 0 12s0 3.93.502 5.814a3.016 3.016 0 0 0 2.122 2.136c1.871.505 9.376.505 9.376.505s7.505 0 9.377-.505a3.015 3.015 0 0 0 2.122-2.136C24 15.93 24 12 24 12s0-3.93-.502-5.814zM9.545 15.568V8.432L15.818 12l-6.273 3.568z"/>
                      </svg>
                    </button>
                  )}
                  <button
                    onClick={() => handleDelete(file.name)}
                    className="px-3 py-1.5 text-sm font-medium text-red-600 bg-red-50 rounded-lg hover:bg-red-100"
                  >
                    <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16" />
                    </svg>
                  </button>
                </div>
              </div>
            </div>
          ))}
        </div>
      ) : (
        <div className="bg-white rounded-xl shadow-sm border border-gray-200 overflow-hidden">
          <table className="w-full">
            <thead className="bg-gray-50">
              <tr className="text-left text-sm text-gray-500 border-b border-gray-200">
                <th className="px-6 py-3 font-medium">Name</th>
                <th className="px-6 py-3 font-medium">Size</th>
                <th className="px-6 py-3 font-medium">Modified</th>
                <th className="px-6 py-3 font-medium">Actions</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-100">
              {files.map((file) => (
                <tr key={file.name} className="hover:bg-gray-50">
                  <td className="px-6 py-4">
                    <div className="flex items-center">
                      {file.is_video ? (
                        <svg className="w-5 h-5 text-gray-400 mr-3" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15 10l4.553-2.276A1 1 0 0121 8.618v6.764a1 1 0 01-1.447.894L15 14M5 18h8a2 2 0 002-2V8a2 2 0 00-2-2H5a2 2 0 00-2 2v8a2 2 0 002 2z" />
                        </svg>
                      ) : (
                        <svg className="w-5 h-5 text-gray-400 mr-3" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
                        </svg>
                      )}
                      <span className="font-medium text-gray-900">{file.name}</span>
                    </div>
                  </td>
                  <td className="px-6 py-4 text-sm text-gray-500">{formatSize(file.size)}</td>
                  <td className="px-6 py-4 text-sm text-gray-500">{formatDate(file.modified)}</td>
                  <td className="px-6 py-4">
                    <div className="flex items-center gap-3">
                      <a
                        href={getFileUrl(file.name)}
                        target="_blank"
                        rel="noopener noreferrer"
                        className="text-sm font-medium text-frigate-600 hover:text-frigate-700"
                      >
                        View
                      </a>
                      <a
                        href={getFileUrl(file.name, true)}
                        className="text-sm font-medium text-gray-600 hover:text-gray-700"
                      >
                        Download
                      </a>
                      {youtubeStatus?.configured && file.is_video && (
                        <button
                          onClick={() => handleUploadToYouTube(file)}
                          className="text-sm font-medium text-red-500 hover:text-red-600"
                        >
                          YouTube
                        </button>
                      )}
                      <button
                        onClick={() => handleDelete(file.name)}
                        className="text-sm font-medium text-red-600 hover:text-red-700"
                      >
                        Delete
                      </button>
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {/* Video Preview Modal */}
      {previewFile && previewFile.is_video && (
        <div
          className="fixed inset-0 bg-black/75 flex items-center justify-center z-50 p-8"
          onClick={() => setPreviewFile(null)}
        >
          <div
            className="bg-white rounded-xl overflow-hidden max-w-4xl w-full"
            onClick={(e) => e.stopPropagation()}
          >
            <div className="flex items-center justify-between p-4 border-b border-gray-200">
              <h3 className="font-medium text-gray-900">{previewFile.name}</h3>
              <button
                onClick={() => setPreviewFile(null)}
                className="text-gray-400 hover:text-gray-600"
              >
                <svg className="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
                </svg>
              </button>
            </div>
            <video
              src={getFileUrl(previewFile.name)}
              controls
              autoPlay
              className="w-full max-h-[70vh]"
            />
          </div>
        </div>
      )}

      {/* YouTube Upload Modal */}
      {uploadFile && (
        <div
          className="fixed inset-0 bg-black/75 flex items-center justify-center z-50 p-8"
          onClick={() => !uploading && setUploadFile(null)}
        >
          <div
            className="bg-white rounded-xl overflow-hidden max-w-lg w-full"
            onClick={(e) => e.stopPropagation()}
          >
            <div className="flex items-center justify-between p-4 border-b border-gray-200">
              <h3 className="font-medium text-gray-900 flex items-center">
                <svg className="w-5 h-5 mr-2 text-red-500" viewBox="0 0 24 24" fill="currentColor">
                  <path d="M23.498 6.186a3.016 3.016 0 0 0-2.122-2.136C19.505 3.545 12 3.545 12 3.545s-7.505 0-9.377.505A3.017 3.017 0 0 0 .502 6.186C0 8.07 0 12 0 12s0 3.93.502 5.814a3.016 3.016 0 0 0 2.122 2.136c1.871.505 9.376.505 9.376.505s7.505 0 9.377-.505a3.015 3.015 0 0 0 2.122-2.136C24 15.93 24 12 24 12s0-3.93-.502-5.814zM9.545 15.568V8.432L15.818 12l-6.273 3.568z"/>
                </svg>
                Upload to YouTube
              </h3>
              {!uploading && (
                <button
                  onClick={() => setUploadFile(null)}
                  className="text-gray-400 hover:text-gray-600"
                >
                  <svg className="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
                  </svg>
                </button>
              )}
            </div>

            <div className="p-6 space-y-4">
              {uploadResult?.url ? (
                <div className="text-center">
                  <div className="text-green-600 mb-4">
                    <svg className="w-16 h-16 mx-auto" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 13l4 4L19 7" />
                    </svg>
                  </div>
                  <p className="text-lg font-medium text-gray-900 mb-2">Upload Complete!</p>
                  <a
                    href={uploadResult.url}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="text-red-600 hover:text-red-700 underline"
                  >
                    View on YouTube
                  </a>
                </div>
              ) : uploadResult?.error ? (
                <div className="text-center">
                  <div className="text-red-600 mb-4">
                    <svg className="w-16 h-16 mx-auto" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
                    </svg>
                  </div>
                  <p className="text-lg font-medium text-gray-900 mb-2">Upload Failed</p>
                  <p className="text-red-600 text-sm">{uploadResult.error}</p>
                </div>
              ) : uploading ? (
                <div className="text-center py-8">
                  <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-red-600 mx-auto mb-4"></div>
                  <p className="text-gray-600">Uploading to YouTube...</p>
                  <p className="text-sm text-gray-500 mt-2">This may take a while for large files</p>
                </div>
              ) : (
                <>
                  <div className="text-sm text-gray-500 mb-4">
                    File: <span className="font-medium text-gray-700">{uploadFile.name}</span>
                  </div>

                  <div>
                    <label className="block text-sm font-medium text-gray-700 mb-1">Title</label>
                    <input
                      type="text"
                      value={uploadTitle}
                      onChange={(e) => setUploadTitle(e.target.value)}
                      className="block w-full rounded-lg border-gray-300 shadow-sm focus:border-red-500 focus:ring-red-500"
                    />
                  </div>

                  <div>
                    <label className="block text-sm font-medium text-gray-700 mb-1">Description</label>
                    <textarea
                      value={uploadDescription}
                      onChange={(e) => setUploadDescription(e.target.value)}
                      rows={3}
                      className="block w-full rounded-lg border-gray-300 shadow-sm focus:border-red-500 focus:ring-red-500"
                    />
                  </div>

                  <div>
                    <label className="block text-sm font-medium text-gray-700 mb-1">Privacy</label>
                    <select
                      value={uploadPrivacy}
                      onChange={(e) => setUploadPrivacy(e.target.value)}
                      className="block w-full rounded-lg border-gray-300 shadow-sm focus:border-red-500 focus:ring-red-500"
                    >
                      <option value="private">Private</option>
                      <option value="unlisted">Unlisted</option>
                      <option value="public">Public</option>
                    </select>
                  </div>

                  {youtubeAccounts.length > 1 && (
                    <div>
                      <label className="block text-sm font-medium text-gray-700 mb-1">Account</label>
                      <select
                        value={uploadAccount}
                        onChange={(e) => setUploadAccount(e.target.value)}
                        className="block w-full rounded-lg border-gray-300 shadow-sm focus:border-red-500 focus:ring-red-500"
                      >
                        {youtubeAccounts.map((acc) => (
                          <option key={acc.name} value={acc.name}>
                            {acc.name}
                          </option>
                        ))}
                      </select>
                    </div>
                  )}

                  <button
                    onClick={handleUploadSubmit}
                    disabled={!uploadTitle}
                    className="w-full px-4 py-2 text-white bg-red-600 rounded-lg hover:bg-red-700 disabled:opacity-50"
                  >
                    Upload to YouTube
                  </button>
                </>
              )}
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
