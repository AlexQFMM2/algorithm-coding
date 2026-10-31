import React from 'react';
import Renderer from '../Renderer/index.jsx';
import styles from './LogRenderer.module.css';

class LogRenderer extends Renderer {
  constructor(props) {
    super(props);

    this.elementRef = React.createRef();
  }

  componentDidUpdate(prevProps, prevState, snapshot) {
    super.componentDidUpdate(prevProps, prevState, snapshot);
    const div = this.elementRef.current;
    div.scrollTop = div.scrollHeight;
  }

  renderData() {
    const { log } = this.props.data;

    return (
      <div className={styles.log} ref={this.elementRef}>
        <div className={styles.content} >{log}</div>
      </div>
    );
  }
}

export default LogRenderer;
