import { useState, useEffect, useCallback } from 'react'

// Types matching the API response
interface Commit {
  hash: string
  short_hash: string
  date: string
  subject: string
  message: string
  author: string
}

interface Snapshot {
  index: number
  commit: Commit
  source: string
  start_line: number
  end_line: number
  change_type: string
  changed_lines: number[]
}

interface AnalyzeResponse {
  function_name: string
  file_path: string
  repo: string
  entity_type: string
  snapshots: Snapshot[]
}

interface SummaryResponse {
  summary: string | null
  cached: boolean
}

interface HistoryItem {
  url: string
  func: string
  entityType: string
  repo: string
  filePath: string
  timestamp: number
}

type EntityType = 'auto' | 'function' | 'class' | 'struct' | 'enum' | 'impl' | 'interface'

const ENTITY_TYPES: { value: EntityType; label: string }[] = [
  { value: 'auto', label: 'Auto-detect' },
  { value: 'function', label: 'Function' },
  { value: 'class', label: 'Class' },
  { value: 'struct', label: 'Struct' },
  { value: 'enum', label: 'Enum' },
  { value: 'impl', label: 'Impl' },
  { value: 'interface', label: 'Interface' },
]

// API client
const API_BASE = 'http://localhost:8000'

// History helpers
const HISTORY_KEY = 'fn-evolution-history'
const MAX_HISTORY = 10

function loadHistory(): HistoryItem[] {
  try {
    const stored = localStorage.getItem(HISTORY_KEY)
    return stored ? JSON.parse(stored) : []
  } catch {
    return []
  }
}

function saveHistory(history: HistoryItem[]) {
  localStorage.setItem(HISTORY_KEY, JSON.stringify(history.slice(0, MAX_HISTORY)))
}

function addToHistory(history: HistoryItem[], item: HistoryItem): HistoryItem[] {
  // Remove duplicate if exists
  const filtered = history.filter(h => !(h.url === item.url && h.func === item.func && h.entityType === item.entityType))
  // Add new item at the beginning
  return [item, ...filtered].slice(0, MAX_HISTORY)
}

async function analyzeFunction(githubUrl: string, functionName: string, entityType: string = 'function'): Promise<AnalyzeResponse> {
  const response = await fetch(`${API_BASE}/api/analyze`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ github_url: githubUrl, function_name: functionName, entity_type: entityType }),
  })
  if (!response.ok) {
    const error = await response.json()
    throw new Error(error.detail || 'Failed to analyze entity')
  }
  return response.json()
}

async function getSummary(githubUrl: string, functionName: string, entityType: string = 'function'): Promise<SummaryResponse> {
  const response = await fetch(`${API_BASE}/api/summary`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ github_url: githubUrl, function_name: functionName, entity_type: entityType }),
  })
  if (!response.ok) {
    throw new Error('Failed to get summary')
  }
  return response.json()
}

// Components
function InputForm({ onSubmit, loading }: { onSubmit: (url: string, func: string, entityType: string) => void; loading: boolean }) {
  const [url, setUrl] = useState('')
  const [func, setFunc] = useState('')
  const [entityType, setEntityType] = useState<EntityType>('auto')

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault()
    if (url && func) {
      onSubmit(url, func, entityType)
    }
  }

  return (
    <form onSubmit={handleSubmit} className="flex gap-4 items-end flex-wrap">
      <div className="flex-1 min-w-[300px]">
        <label className="block text-sm text-gray-400 mb-1">GitHub URL</label>
        <input
          type="text"
          value={url}
          onChange={(e) => setUrl(e.target.value)}
          placeholder="https://github.com/owner/repo/blob/main/path/file.rs"
          className="w-full px-3 py-2 bg-gray-800 border border-gray-700 rounded text-white placeholder-gray-500 focus:outline-none focus:border-blue-500"
        />
      </div>
      <div className="w-32">
        <label className="block text-sm text-gray-400 mb-1">Type</label>
        <select
          value={entityType}
          onChange={(e) => setEntityType(e.target.value as EntityType)}
          className="w-full px-3 py-2 bg-gray-800 border border-gray-700 rounded text-white focus:outline-none focus:border-blue-500"
        >
          {ENTITY_TYPES.map(t => (
            <option key={t.value} value={t.value}>{t.label}</option>
          ))}
        </select>
      </div>
      <div className="w-48">
        <label className="block text-sm text-gray-400 mb-1">Name</label>
        <input
          type="text"
          value={func}
          onChange={(e) => setFunc(e.target.value)}
          placeholder="my_function"
          className="w-full px-3 py-2 bg-gray-800 border border-gray-700 rounded text-white placeholder-gray-500 focus:outline-none focus:border-blue-500"
        />
      </div>
      <button
        type="submit"
        disabled={loading || !url || !func}
        className="px-6 py-2 bg-blue-600 hover:bg-blue-700 disabled:bg-gray-700 disabled:cursor-not-allowed text-white rounded font-medium transition-colors"
      >
        {loading ? 'Analyzing...' : 'Analyze'}
      </button>
    </form>
  )
}

function SnapshotNav({
  current,
  total,
  snapshot,
  onPrev,
  onNext,
}: {
  current: number
  total: number
  snapshot: Snapshot
  onPrev: () => void
  onNext: () => void
}) {
  const date = new Date(snapshot.commit.date).toLocaleDateString()

  return (
    <div className="flex items-center justify-between bg-gray-800 px-4 py-3 rounded">
      <button
        onClick={onPrev}
        disabled={current === 0}
        className="px-3 py-1 bg-gray-700 hover:bg-gray-600 disabled:opacity-50 disabled:cursor-not-allowed rounded"
      >
        ◀ Older
      </button>
      <div className="text-center">
        <div className="text-sm text-gray-400">
          [{current + 1}/{total}] {date} | {snapshot.commit.short_hash} |{' '}
          <span className={snapshot.change_type === 'created' ? 'text-green-400' : 'text-yellow-400'}>
            {snapshot.change_type.toUpperCase()}
          </span>
        </div>
        <div className="text-white font-medium">{snapshot.commit.subject}</div>
      </div>
      <button
        onClick={onNext}
        disabled={current === total - 1}
        className="px-3 py-1 bg-gray-700 hover:bg-gray-600 disabled:opacity-50 disabled:cursor-not-allowed rounded"
      >
        Newer ▶
      </button>
    </div>
  )
}

function SourceCode({ snapshot }: { snapshot: Snapshot }) {
  const lines = snapshot.source.split('\n')
  const changedSet = new Set(snapshot.changed_lines)

  return (
    <div className="bg-gray-900 rounded overflow-x-auto">
      <pre className="p-4">
        {lines.map((line, i) => {
          const lineNum = snapshot.start_line + i
          const isChanged = changedSet.has(i)
          return (
            <div key={i} className={`code-line ${isChanged ? 'changed' : ''}`}>
              <span className={`line-number inline-block w-12 text-right pr-4 ${isChanged ? 'text-green-500 font-bold' : 'text-gray-600'}`}>
                {lineNum}
              </span>
              <span className={isChanged ? 'text-green-400' : 'text-gray-300'}>{line || ' '}</span>
            </div>
          )
        })}
      </pre>
    </div>
  )
}

function Summary({ summary, loading }: { summary: string | null; loading: boolean }) {
  if (loading) {
    return (
      <div className="bg-gray-800/50 border border-gray-700 rounded-lg p-4">
        <div className="text-gray-400 animate-pulse flex items-center gap-2">
          <svg className="w-4 h-4 animate-spin" viewBox="0 0 24 24" fill="none">
            <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4"/>
            <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z"/>
          </svg>
          Generating summary...
        </div>
      </div>
    )
  }

  if (!summary) {
    return null
  }

  return (
    <div className="bg-gradient-to-r from-gray-800/50 to-gray-800/30 border border-gray-700 rounded-lg p-5">
      <div className="flex items-center gap-2 text-xs font-medium text-gray-500 uppercase tracking-wider mb-3">
        <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13 16h-1v-4h-1m1-4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
        </svg>
        Summary
      </div>
      <div className="text-gray-300 text-sm leading-relaxed max-w-none">
        {summary}
      </div>
    </div>
  )
}

function History({
  history,
  onSelect,
  onClear
}: {
  history: HistoryItem[]
  onSelect: (item: HistoryItem) => void
  onClear: () => void
}) {
  if (history.length === 0) {
    return null
  }

  return (
    <div className="bg-gray-800/30 border border-gray-700/50 rounded-lg p-4">
      <div className="flex items-center justify-between mb-3">
        <div className="text-xs font-medium text-gray-500 uppercase tracking-wider">
          Recent Searches
        </div>
        <button
          onClick={onClear}
          className="text-xs text-gray-500 hover:text-gray-300 transition-colors"
        >
          Clear
        </button>
      </div>
      <div className="space-y-2">
        {history.map((item, i) => (
          <button
            key={`${item.url}-${item.func}-${item.entityType}-${i}`}
            onClick={() => onSelect(item)}
            className="w-full text-left px-3 py-2 bg-gray-800/50 hover:bg-gray-700/50 rounded border border-transparent hover:border-gray-600 transition-all group"
          >
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-2">
                <span className="text-xs px-2 py-0.5 bg-gray-700 rounded text-gray-400">
                  {item.entityType || 'function'}
                </span>
                <span className="text-blue-400 font-mono text-sm">{item.func}</span>
              </div>
              <span className="text-xs text-gray-500">
                {new Date(item.timestamp).toLocaleDateString()}
              </span>
            </div>
            <div className="text-xs text-gray-500 truncate mt-1">
              {item.repo} / {item.filePath}
            </div>
          </button>
        ))}
      </div>
    </div>
  )
}

function App() {
  const [data, setData] = useState<AnalyzeResponse | null>(null)
  const [currentIndex, setCurrentIndex] = useState(0)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [summary, setSummary] = useState<string | null>(null)
  const [summaryLoading, setSummaryLoading] = useState(false)
  const [history, setHistory] = useState<HistoryItem[]>(() => loadHistory())
  const [currentEntityType, setCurrentEntityType] = useState<string>('function')

  const handleSubmit = async (url: string, func: string, entityType: string = 'auto') => {
    setLoading(true)
    setError(null)
    setData(null)
    setSummary(null)

    try {
      const result = await analyzeFunction(url, func, entityType)
      setData(result)
      setCurrentIndex(result.snapshots.length - 1) // Start at newest
      // Use the detected entity type from the API
      const detectedType = result.entity_type
      setCurrentEntityType(detectedType)

      // Add to history on success (store the detected type, not "auto")
      const newHistory = addToHistory(history, {
        url,
        func,
        entityType: detectedType,
        repo: result.repo,
        filePath: result.file_path,
        timestamp: Date.now(),
      })
      setHistory(newHistory)
      saveHistory(newHistory)

      // Fetch summary in background using the detected type
      setSummaryLoading(true)
      getSummary(url, func, detectedType)
        .then((s) => setSummary(s.summary))
        .catch(() => {})
        .finally(() => setSummaryLoading(false))
    } catch (e) {
      setError(e instanceof Error ? e.message : 'An error occurred')
    } finally {
      setLoading(false)
    }
  }

  const handleHistorySelect = (item: HistoryItem) => {
    handleSubmit(item.url, item.func, item.entityType || 'function')
  }

  const handleClearHistory = () => {
    setHistory([])
    localStorage.removeItem(HISTORY_KEY)
  }

  const handleKeyDown = useCallback(
    (e: KeyboardEvent) => {
      if (!data) return
      if (e.key === 'ArrowLeft' || e.key === 'k') {
        setCurrentIndex((i) => Math.max(0, i - 1))
      } else if (e.key === 'ArrowRight' || e.key === 'j') {
        setCurrentIndex((i) => Math.min(data.snapshots.length - 1, i + 1))
      }
    },
    [data]
  )

  useEffect(() => {
    window.addEventListener('keydown', handleKeyDown)
    return () => window.removeEventListener('keydown', handleKeyDown)
  }, [handleKeyDown])

  const snapshot = data?.snapshots[currentIndex]

  return (
    <div className="min-h-screen bg-gray-900 text-gray-100 p-6">
      <div className="max-w-6xl mx-auto space-y-6">
        {/* Header */}
        <div className="text-center mb-8">
          <h1 className="text-3xl font-bold text-white mb-2">Code Evolution Viewer</h1>
          <p className="text-gray-400">View the git history of functions, classes, structs, and more on GitHub</p>
        </div>

        {/* Input Form */}
        <InputForm onSubmit={handleSubmit} loading={loading} />

        {/* History - show when no data is loaded */}
        {!data && !loading && (
          <History
            history={history}
            onSelect={handleHistorySelect}
            onClear={handleClearHistory}
          />
        )}

        {/* Error */}
        {error && (
          <div className="bg-red-900/50 border border-red-700 text-red-200 px-4 py-3 rounded">
            {error}
          </div>
        )}

        {/* Results */}
        {data && snapshot && (
          <>
            {/* Entity Info */}
            <div className="bg-blue-900/30 px-4 py-2 rounded text-center">
              <span className="text-blue-400 font-medium capitalize">{currentEntityType}:</span>{' '}
              <span className="text-white">{data.function_name}</span>
              <span className="text-gray-500 mx-2">|</span>
              <span className="text-blue-400 font-medium">File:</span>{' '}
              <span className="text-white">{data.file_path}</span>
              <span className="text-gray-500 mx-2">|</span>
              <span className="text-blue-400 font-medium">Repo:</span>{' '}
              <span className="text-white">{data.repo}</span>
            </div>

            {/* Summary */}
            <Summary summary={summary} loading={summaryLoading} />

            {/* Navigation */}
            <SnapshotNav
              current={currentIndex}
              total={data.snapshots.length}
              snapshot={snapshot}
              onPrev={() => setCurrentIndex((i) => Math.max(0, i - 1))}
              onNext={() => setCurrentIndex((i) => Math.min(data.snapshots.length - 1, i + 1))}
            />

            {/* Source Code */}
            <SourceCode snapshot={snapshot} />

            {/* Keyboard hints */}
            <div className="text-center text-sm text-gray-500">
              Use <kbd className="px-2 py-1 bg-gray-800 rounded">←</kbd> / <kbd className="px-2 py-1 bg-gray-800 rounded">→</kbd> or{' '}
              <kbd className="px-2 py-1 bg-gray-800 rounded">j</kbd> / <kbd className="px-2 py-1 bg-gray-800 rounded">k</kbd> to navigate
            </div>
          </>
        )}
      </div>
    </div>
  )
}

export default App
