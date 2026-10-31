import React from 'react';
export function Ellipsis({className, children}) {
  return <h3 className={className}>{children}</h3>;
}
// Local layout shell for upstream Layout; sizing follows the modal, not the app.
export class ResizableContainer extends React.Component {
  render() {
    return <div className="av-layout" data-horizontal={this.props.horizontal || undefined}>{this.props.children}</div>;
  }
}
