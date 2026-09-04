/**
 * SystemHealth.jsx - 系统健康面板
 *
 * 展示 /api/health 返回的数据：引擎状态、数据概览、Schema 校验、
 * 写失败计数、内存漂移检测。
 */

import React, { useState, useEffect } from 'react';
import { Card, Row, Col, Tag, Button, Alert, Spin, Descriptions, Typography } from 'antd';
import { CheckCircleOutlined, CloseCircleOutlined, WarningOutlined, ReloadOutlined, SyncOutlined } from '@ant-design/icons';
import { authFetch } from '../../api';
import AdminShell from './AdminShell';

const { Text } = Typography;

function SystemHealth() {
  const [health, setHealth] = useState(null);
  const [loading, setLoading] = useState(true);

  const loadHealth = async () => {
    setLoading(true);
    try {
      const resp = await authFetch('/api/health');
      const data = await resp.json();
      setHealth(data);
    } catch (e) {
      setHealth({ ok: false, error: e.message });
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { loadHealth(); }, []);

  const handleRebuild = async () => {
    try {
      const resp = await authFetch('/api/rebuild');
      if (resp.ok) {
        message.success('索引重建已触发');
      } else {
        const data = await resp.json().catch(() => ({}));
        message.error(data.error || data.detail || '重建失败');
      }
    } catch {
      message.error('重建失败');
    }
  };

  if (loading) return <div style={{ textAlign: 'center', padding: 60 }}><Spin size="large" /></div>;

  if (!health?.ok) {
    return (
      <AdminShell title="系统健康">
        <Alert type="error" message="健康检查失败" description={health?.error || '无法连接服务'} />
      </AdminShell>
    );
  }

  const { engine_ready, db_type, schema_issues, write_failures, counts, drift } = health;
  const hasFailures = Object.values(write_failures || {}).some(v => v > 0);
  const hasDrift = !drift?.ok;
  const hasSchemaIssues = schema_issues?.length > 0;

  return (
    <AdminShell
      title="系统健康"
      description="搜索引擎、数据库、索引状态实时监控"
      extra={<Button icon={<ReloadOutlined />} onClick={loadHealth} loading={loading}>刷新</Button>}
    >
      {/* 漂移告警 */}
      {hasDrift && drift.warnings?.map((w, i) => (
        <Alert key={i} type="warning" showIcon icon={<WarningOutlined />}
          message={w}
          action={<Button size="small" type="primary" icon={<SyncOutlined />} onClick={handleRebuild}>重建索引</Button>}
          style={{ marginBottom: 12 }}
        />
      ))}

      {/* 核心状态卡片 */}
      <Row gutter={[16, 16]} style={{ marginBottom: 20 }}>
        <Col span={8}>
          <Card style={{ borderRadius: 12, textAlign: 'center' }}>
            <div style={{ fontSize: 13, color: '#999', marginBottom: 8 }}>搜索引擎</div>
            {engine_ready
              ? <Tag color="success" style={{ fontSize: 16, padding: '4px 16px' }}><CheckCircleOutlined /> 运行中</Tag>
              : <Tag color="error" style={{ fontSize: 16, padding: '4px 16px' }}><CloseCircleOutlined /> 未就绪</Tag>
            }
          </Card>
        </Col>
        <Col span={8}>
          <Card style={{ borderRadius: 12, textAlign: 'center' }}>
            <div style={{ fontSize: 13, color: '#999', marginBottom: 8 }}>数据库</div>
            <Tag color="blue" style={{ fontSize: 16, padding: '4px 16px' }}>{db_type || '未知'}</Tag>
          </Card>
        </Col>
        <Col span={8}>
          <Card style={{ borderRadius: 12, textAlign: 'center' }}>
            <div style={{ fontSize: 13, color: '#999', marginBottom: 8 }}>写失败计数</div>
            {hasFailures
              ? <Tag color="error" style={{ fontSize: 16, padding: '4px 16px' }}><WarningOutlined /> {Object.values(write_failures).reduce((a, b) => a + b, 0)}</Tag>
              : <Tag color="success" style={{ fontSize: 16, padding: '4px 16px' }}><CheckCircleOutlined /> 0</Tag>
            }
          </Card>
        </Col>
      </Row>

      {/* 数据概览 */}
      <Card title="数据概览" style={{ borderRadius: 12, marginBottom: 20 }}>
        <Row gutter={[16, 12]}>
          {Object.entries(counts || {}).map(([table, count]) => (
            <Col span={8} key={table}>
              <div style={{ display: 'flex', justifyContent: 'space-between', padding: '8px 0', borderBottom: '1px solid #f0f0f0' }}>
                <Text type="secondary">{table}</Text>
                <Text strong style={{ fontSize: 16 }}>{count ?? '-'}</Text>
              </div>
            </Col>
          ))}
        </Row>
      </Card>

      {/* Schema 校验 + 写失败明细 */}
      <Row gutter={[16, 16]}>
        <Col span={12}>
          <Card title="Schema 校验" style={{ borderRadius: 12 }}>
            {hasSchemaIssues
              ? schema_issues.map((issue, i) => (
                <Alert key={i} type="warning" message={issue} style={{ marginBottom: 8 }} />
              ))
              : <Text type="secondary">所有表结构校验通过</Text>
            }
          </Card>
        </Col>
        <Col span={12}>
          <Card title="写失败明细" style={{ borderRadius: 12 }}>
            {!hasFailures
              ? <Text type="secondary">无写失败记录</Text>
              : Object.entries(write_failures).filter(([, v]) => v > 0).map(([key, count]) => (
                <div key={key} style={{ display: 'flex', justifyContent: 'space-between', padding: '4px 0' }}>
                  <Text>{key}</Text>
                  <Tag color="error">{count}</Tag>
                </div>
              ))
            }
          </Card>
        </Col>
      </Row>
    </AdminShell>
  );
}

export default SystemHealth;
