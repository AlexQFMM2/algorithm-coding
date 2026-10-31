import Array2DRenderer from '../Array2DRenderer/index.jsx';

class Array1DRenderer extends Array2DRenderer {
  get oneDimensional() { return true; }
}

export default Array1DRenderer;
