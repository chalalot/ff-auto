import React from 'react'
import { useQuery } from '@tanstack/react-query'
import { monitorApi } from '@/api/monitor'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Progress } from '@/components/ui/progress'
import { Cpu, HardDrive, Database, Folder } from 'lucide-react'

export const MonitorPage: React.FC = () => {
  const { data: health } = useQuery({
    queryKey: ['monitor', 'health'],
    queryFn: monitorApi.getHealth,
    refetchInterval: 5000,
  })
  const { data: dbStats } = useQuery({
    queryKey: ['monitor', 'db-stats'],
    queryFn: monitorApi.getDbStats,
    refetchInterval: 10000,
  })
  const { data: filesystem } = useQuery({
    queryKey: ['monitor', 'filesystem'],
    queryFn: monitorApi.getFilesystem,
    refetchInterval: 10000,
  })

  const formatBytes = (bytes: number) => {
    const gb = bytes / (1024 ** 3)
    return `${gb.toFixed(1)} GB`
  }

  return (
    <div className="p-6 space-y-6">
      <h1 className="text-xl font-bold">System Monitor</h1>

      {/* System Health */}
      {health && (
        <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
          <Card>
            <CardHeader className="pb-2">
              <CardTitle className="text-sm flex items-center gap-2">
                <Cpu className="w-4 h-4" />CPU Usage
              </CardTitle>
            </CardHeader>
            <CardContent>
              <div className="text-2xl font-bold">{health.cpu_percent.toFixed(1)}%</div>
              <Progress value={health.cpu_percent} className="mt-2 h-2" />
            </CardContent>
          </Card>

          <Card>
            <CardHeader className="pb-2">
              <CardTitle className="text-sm flex items-center gap-2">
                <Cpu className="w-4 h-4" />Memory
              </CardTitle>
            </CardHeader>
            <CardContent>
              <div className="text-2xl font-bold">{health.ram.percent.toFixed(1)}%</div>
              <div className="text-xs text-muted-foreground mt-1">
                {formatBytes(health.ram.used)} / {formatBytes(health.ram.total)}
              </div>
              <Progress value={health.ram.percent} className="mt-2 h-2" />
            </CardContent>
          </Card>

          <Card>
            <CardHeader className="pb-2">
              <CardTitle className="text-sm flex items-center gap-2">
                <HardDrive className="w-4 h-4" />Disk
              </CardTitle>
            </CardHeader>
            <CardContent>
              <div className="text-2xl font-bold">{health.disk.percent.toFixed(1)}%</div>
              <div className="text-xs text-muted-foreground mt-1">
                {formatBytes(health.disk.used)} / {formatBytes(health.disk.total)}
              </div>
              <Progress value={health.disk.percent} className="mt-2 h-2" />
            </CardContent>
          </Card>
        </div>
      )}

      {/* DB Stats */}
      {dbStats && (
        <Card>
          <CardHeader>
            <CardTitle className="text-sm flex items-center gap-2">
              <Database className="w-4 h-4" />Database
            </CardTitle>
          </CardHeader>
          <CardContent>
            <pre className="text-xs text-muted-foreground whitespace-pre-wrap">
              {JSON.stringify(dbStats, null, 2)}
            </pre>
          </CardContent>
        </Card>
      )}

      {/* Filesystem */}
      {filesystem && (
        <Card>
          <CardHeader>
            <CardTitle className="text-sm flex items-center gap-2">
              <Folder className="w-4 h-4" />Filesystem
            </CardTitle>
          </CardHeader>
          <CardContent>
            <pre className="text-xs text-muted-foreground whitespace-pre-wrap">
              {JSON.stringify(filesystem, null, 2)}
            </pre>
          </CardContent>
        </Card>
      )}
    </div>
  )
}
