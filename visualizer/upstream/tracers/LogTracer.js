import { sprintf } from 'sprintf-js';
import Tracer from './Tracer.jsx';
import LogRenderer from '../renderers/LogRenderer/index.jsx';

class LogTracer extends Tracer {
  getRendererClass() {
    return LogRenderer;
  }

  set(log = '') {
    this.log = log;
    super.set();
  }

  print(message) {
    this.log += message;
  }

  println(message) {
    this.print(message + '\n');
  }

  printf(format, ...args) {
    this.print(sprintf(format, ...args));
  }
}

export default LogTracer;
