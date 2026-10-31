import React from 'react';
import Renderer from '../Renderer/index.jsx';
import styles from './Array2DRenderer.module.css';
import { classes } from 'common/util';

class Array2DRenderer extends Renderer {
  constructor(props) {
    super(props);

    this.togglePan(false);
    this.toggleZoom(false);
  }

  renderData() {
    const { data } = this.props.data;

    const isArray1D = this.oneDimensional === true;
    let longestRow = data.reduce((longestRow, row) => longestRow.length < row.length ? row : longestRow, []);

    return (
      <table aria-label={this.props.title} className={styles.array_2d}
             style={{ marginLeft: -this.centerX * 2, marginTop: -this.centerY * 2, transform: `scale(${this.zoom})` }}>
        <tbody>
        <tr className={styles.row}>
          {
            !isArray1D &&
            <td className={classes(styles.col, styles.index)} />
          }
          {
            longestRow.map((_, i) => (
              <td className={classes(styles.col, styles.index)} key={i}>
                <span className={styles.value}>{i}</span>
              </td>
            ))
          }
        </tr>
        {
          data.map((row, i) => (
            <tr className={styles.row} key={i}>
              {
                !isArray1D &&
                <td className={classes(styles.col, styles.index)}>
                  <span className={styles.value}>{i}</span>
                </td>
              }
              {
                row.map((col, j) => (
                  <td className={classes(styles.col, col.selected && styles.selected, col.patched && styles.patched)}
                      key={j} data-selected={col.selected || undefined} data-patched={col.patched || undefined}
                      aria-label={`位置 ${j}，值 ${col.value}${col.selected ? "，已选中" : ""}${col.patched ? "，当前操作" : ""}`}>
                    <span className={styles.value}>{this.toString(col.value)}</span>
                  </td>
                ))
              }
            </tr>
          ))
        }
        </tbody>
      </table>
    );
  }
}

export default Array2DRenderer;
