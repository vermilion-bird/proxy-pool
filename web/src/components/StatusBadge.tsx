export default function StatusBadge({ status }: { status: string }) {
  const cls = `status-badge status-${status.toLowerCase()}`
  return <span className={cls}>{status}</span>
}
