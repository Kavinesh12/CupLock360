import { Result } from 'antd'

export default function ComingSoon({ title, day }: { title: string; day: number }) {
  return <Result status="info" title={title} subTitle={`This module is built on Day ${day} of the plan.`} />
}
